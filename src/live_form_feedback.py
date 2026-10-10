"""Run the full live system: cameras to 3D to assessment to Unity."""
import sys, os, time, argparse, json, hashlib, csv
import numpy as np
import cv2
from ultralytics import YOLO

from live_triangulate import load_rig, open_camera, pick_device, draw_reprojection
from multiview_triangulate import triangulate_skeleton, N_JOINTS
from dlt_triangulation import project
from kalman_smoother import SkeletonKalman
from one_euro import SkeletonOneEuro


class PassThrough:
    """--filter none."""

    def update(self, joints_3d, dt=None):
        return joints_3d
import metrics as M
from rep_engine import (SquatRepEngine, DOMINANCE_CENTRE, DOMINANCE_BAND,
                        UPRIGHT_DEG, GAP_MIN_FRAMES, REP_ABANDON_S,
                        calibration_femur, FEMUR_RANGE_MM)
from session_io import SessionRecorder, meta_from_body_frame
from set_video import SetVideoWriter
from set_export import write_set


def refresh_report(dirpath, quiet=False):
    """Redraw the session's HTML report from the set dumps written so far."""
    try:
        tools = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")
        if tools not in sys.path:
            sys.path.insert(0, tools)
        from report_session import write_report
        path = write_report(dirpath)
        if path and not quiet:
            print(f"--- report -> file://{os.path.abspath(path)}")
        return path
    except Exception as exc:
        print(f"!! could not refresh the report: {exc}")
        return None

CONF_THRESH, MIN_VIEWS = 0.5, 2


MATCH_RADIUS_PX = 250.0
_PREV_HIP3D = None
_LAST_RAW = None
_DISPLAY_FILTER = None
_LAST_DISPLAY = None
_LAST_PTS = None
_LAST_CONF = None

OPT = {"drain": False, "cam_fps": 30.0, "undistort": True,
       "drain_mode": "formula", "edge_ms": 8.0}
MAX_FLUSH = 6


class StageTimer:
    """Wall-clock cost of each pipeline stage, one CSV row per processed frame."""

    COLS = ("frame", "t", "cycle_ms", "capture_ms", "pose_ms", "triangulate_ms",
            "filter_ms", "assess_ms", "send_ms", "draw_ms", "other_ms",
            "views", "tracked")

    def __init__(self, path):
        self.path = path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.f = open(path, "w", newline="")
        self.w = csv.writer(self.f)
        self.w.writerow(self.COLS)
        self.n = 0
        self._prev = None
        self._stage = {}
        self.rows = []

    def reset(self):
        self._stage = {}

    def new_set(self):
        """A set boundary drops the marks AND the previous timestamp, so the wait for Unity's Start is not charged to the set's first frame."""
        self._stage = {}
        self._prev = None

    def mark(self, stage, seconds):
        self._stage[stage] = self._stage.get(stage, 0.0) + seconds * 1000.0

    def commit(self, t, views, tracked):
        now = time.perf_counter()
        cycle = (now - self._prev) * 1000.0 if self._prev is not None else float("nan")
        self._prev = now
        named = sum(self._stage.get(k, 0.0)
                    for k in ("capture", "pose", "triangulate", "filter",
                              "assess", "send", "draw"))
        other = cycle - named if cycle == cycle else float("nan")
        row = [self.n, round(t, 4), _ms(cycle),
               _ms(self._stage.get("capture")), _ms(self._stage.get("pose")),
               _ms(self._stage.get("triangulate")), _ms(self._stage.get("filter")),
               _ms(self._stage.get("assess")), _ms(self._stage.get("send")),
               _ms(self._stage.get("draw")), _ms(other), views, tracked]
        self.w.writerow(row)
        self.rows.append(row)
        self.n += 1
        if self.n % 25 == 0:
            self.f.flush()
        self.reset()

    def close(self):
        try:
            self.f.flush()
            self.f.close()
        except Exception:
            pass
        return self.summary()

    def summary(self):
        """Processing rate and per-stage cost over the whole run."""
        import numpy as _np
        if len(self.rows) < 3:
            return "timing: too few frames to summarise"
        A = _np.array([[(_np.nan if v in (None, "") else v) for v in r[2:11]]
                       for r in self.rows], float)
        cyc = A[1:, 0]
        cyc = cyc[_np.isfinite(cyc)]
        fps = 1000.0 / cyc
        out = [f"\nSTAGE TIMING  ({self.n} frames)  -> {self.path}",
               "  processing rate (fps)   "
               f"mean {fps.mean():.1f}   median {_np.median(fps):.1f}   "
               f"SD {fps.std(ddof=1):.1f}   5th pct {_np.percentile(fps, 5):.1f}",
               f"  cycle time (ms)         mean {cyc.mean():.1f}   "
               f"median {_np.median(cyc):.1f}   worst {cyc.max():.1f}",
               "  stage                     mean ms    % of cycle"]
        names = ("capture", "pose", "triangulate", "filter",
                 "assess", "send", "draw", "other")
        for k, name in enumerate(names):
            col = A[1:, k + 1]
            col = col[_np.isfinite(col)]
            if col.size == 0:
                continue
            out.append(f"  {name:<22} {col.mean():9.2f} {100*col.mean()/cyc.mean():11.1f}")
        return "\n".join(out)


def _ms(x):
    """Round to 0.01 ms, and keep an unmeasured stage empty rather than zero."""
    if x is None:
        return ""
    if x != x:
        return ""
    return round(float(x), 3)


TIMER = None


def pick_subject(res, expected_xy=None):
    """Pick the subject in one view, preferring the box nearest `expected_xy` so that every camera picks the same person."""
    kp = res.keypoints
    if kp is None or kp.xy is None or kp.xy.shape[0] == 0:
        return None, None
    boxes = res.boxes
    idx = 0
    if boxes is not None and getattr(boxes, "xywh", None) is not None and len(boxes.xywh) > 0:
        wh = boxes.xywh.cpu().numpy()
        if expected_xy is not None and np.all(np.isfinite(expected_xy)):
            d = np.linalg.norm(wh[:, :2] - np.asarray(expected_xy, float), axis=1)
            idx = int(d.argmin())
            if d[idx] > MATCH_RADIUS_PX:
                idx = int((wh[:, 2] * wh[:, 3]).argmax())
        else:
            idx = int((wh[:, 2] * wh[:, 3]).argmax())
    xy = kp.xy[idx].cpu().numpy()
    conf = kp.conf[idx].cpu().numpy() if kp.conf is not None else np.ones(xy.shape[0])
    return xy, conf


def load_fixed_up():
    """The rig's true vertical from calib/vertical.json as a unit vector, or None if it has not been measured yet."""
    try:
        d = json.load(open("calib/vertical.json"))
        u = np.array(d["up"], float)
        return u / np.linalg.norm(u)
    except Exception:
        return None


def enough_joints(kp):
    """True if the joints we need for calibration are all present."""
    if kp is None:
        return False
    need = [M.L_SHO, M.R_SHO, M.L_HIP, M.R_HIP, M.L_KNE, M.R_KNE, M.L_ANK, M.R_ANK]
    return all(np.all(np.isfinite(kp[j])) for j in need)


CALIB_STILL_MM = 40.0
CALIB_MIN_SHARE = 0.6

CALIB_FAIL = {
    "joints": "Calibration failed: not all joints were visible. "
              "Step fully into view of all three cameras.",
    "upright": "Calibration failed: Stand still with your knees straight.",
    "still": "Calibration failed: Stand still with your knees straight.",
    "femur": "Calibration failed: leg length could not be measured reliably. "
             "Stand facing the cameras with both legs in view.",
}


def accept_calibration(samples, n_cycles):
    """Keep the capture frames that are freshly triangulated, upright and still."""
    need = max(GAP_MIN_FRAMES, int(np.ceil(CALIB_MIN_SHARE * n_cycles)))
    fresh = [kp for kp, ok in samples if ok]
    if len(fresh) < need:
        return [], "joints"
    upright = [kp for kp in fresh if M.knee_signal(kp) > UPRIGHT_DEG]
    if len(upright) < need:
        return [], "upright"
    pel = np.array([(kp[M.L_HIP] + kp[M.R_HIP]) / 2.0 for kp in upright])
    sho = np.array([(kp[M.L_SHO] + kp[M.R_SHO]) / 2.0 for kp in upright])
    dev = np.maximum(np.linalg.norm(pel - np.median(pel, 0), axis=1),
                     np.linalg.norm(sho - np.median(sho, 0), axis=1))
    still = [kp for kp, d in zip(upright, dev) if d <= CALIB_STILL_MM]
    if len(still) < need:
        return [], "still"
    fm = calibration_femur(still)
    if not (np.isfinite(fm) and FEMUR_RANGE_MM[0] <= fm <= FEMUR_RANGE_MM[1]):
        return [], "femur"
    return still, None


def grab(model, caps, order, indices, rig, kalman, device, prev_t):
    """One pipeline iteration -> (sm3d, frames, valid, t, dt)."""
    global _PREV_HIP3D, _LAST_RAW, _LAST_PTS, _LAST_CONF, _LAST_DISPLAY
    _t0 = time.perf_counter()
    if OPT["drain"] and prev_t is not None and OPT["drain_mode"] == "formula":
        k = int(round(OPT["cam_fps"] * (time.time() - prev_t))) - 1
        for _ in range(max(0, min(k, MAX_FLUSH))):
            for i in order:
                caps[i].grab()
        for i in order:
            caps[i].grab()
    elif OPT["drain"] and prev_t is not None:
        edge = OPT["edge_ms"]
        for _ in range(MAX_FLUSH + 1):
            slow = 0
            for i in order:
                g0 = time.perf_counter()
                caps[i].grab()
                if (time.perf_counter() - g0) * 1000.0 > edge:
                    slow += 1
            if slow == len(order):
                break
    else:
        for i in order:
            caps[i].grab()
    frames, valid = [], []
    for i in order:
        ok, f = caps[i].retrieve()
        if ok and f is not None:
            frames.append(f); valid.append(i)
    if TIMER is not None:
        TIMER.mark("capture", time.perf_counter() - _t0)
    if len(frames) < 2:
        _LAST_RAW = _LAST_PTS = _LAST_CONF = None
        return None, None, None, None, None
    _t1 = time.perf_counter()
    results = model(frames, verbose=False, device=device)
    if TIMER is not None:
        TIMER.mark("pose", time.perf_counter() - _t1)
    _t2 = time.perf_counter()
    pts = np.full((len(rig), N_JOINTS, 2), np.nan)
    conf = np.zeros((len(rig), N_JOINTS))
    for k, i in enumerate(valid):
        ri = indices.index(i)
        exp = None
        if _PREV_HIP3D is not None and np.all(np.isfinite(_PREV_HIP3D)):
            try:
                exp = project(rig[ri].P, _PREV_HIP3D)
            except Exception:
                exp = None
        xy, cf = pick_subject(results[k], expected_xy=exp)
        if xy is not None:
            pts[ri] = xy; conf[ri] = cf
    raw3d, _ = triangulate_skeleton(rig, pts, conf, conf_thresh=CONF_THRESH,
                                   min_views=MIN_VIEWS,
                                   undistort=OPT["undistort"])
    _LAST_RAW, _LAST_PTS, _LAST_CONF = raw3d, pts, conf
    if TIMER is not None:
        TIMER.mark("triangulate", time.perf_counter() - _t2)
    _t3 = time.perf_counter()
    t = time.time()
    dt = t - prev_t if prev_t else 1.0 / 30.0
    sm3d = kalman.update(raw3d, dt)
    _LAST_DISPLAY = (_DISPLAY_FILTER.update(raw3d, dt)
                     if _DISPLAY_FILTER is not None else sm3d)
    if TIMER is not None:
        TIMER.mark("filter", time.perf_counter() - _t3)
    if sm3d is not None:
        mhip = (sm3d[M.L_HIP] + sm3d[M.R_HIP]) / 2.0
        _PREV_HIP3D = mhip if np.all(np.isfinite(mhip)) else None
    return sm3d, frames, valid, t, dt


_win = {}


def _show_win(win, img, pos, width):
    """One resizable, movable window; resize/move applied AFTER first imshow."""
    if win not in _win:
        cv2.namedWindow(win, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)
        try:
            cv2.moveWindow(win, pos[0], pos[1])
        except Exception:
            pass
        _win[win] = False
    cv2.imshow(win, img)
    if not _win[win]:
        h, w = img.shape[:2]
        try:
            cv2.resizeWindow(win, width, max(1, int(width * h / w)))
        except Exception:
            pass
        _win[win] = True


CLEAN_VIDEO = False
SHOW_CAMS = None


def show(frames, valid, indices, rig, sm3d, tile_w=640, banner=None):
    """One separate, movable, full-resolution window per camera (two on top, one below)."""
    for k, i in enumerate(valid):
        if SHOW_CAMS is not None and i not in SHOW_CAMS:
            continue
        disp = frames[k]
        if CLEAN_VIDEO:
            disp = disp.copy()
            pos = (20 + (k % 2) * (tile_w + 30), 60 + (k // 2) * (int(tile_w * 9 / 16) + 80))
            _show_win(f"cam{i}", disp, pos, tile_w)
            continue
        draw_reprojection(disp, rig[indices.index(i)].P, sm3d)
        cv2.putText(disp, f"cam{i}", (12, 42), cv2.FONT_HERSHEY_SIMPLEX, 1.3, (0, 255, 0), 3)
        if banner:
            cv2.putText(disp, banner, (12, disp.shape[0] // 2),
                        cv2.FONT_HERSHEY_SIMPLEX, 2.0, (0, 255, 255), 5)
        pos = (20 + (k % 2) * (tile_w + 30), 60 + (k // 2) * (int(tile_w * 9 / 16) + 80))
        _show_win(f"cam{i}  form feedback (q quits)", disp, pos, tile_w)
    return cv2.waitKey(1) & 0xFF


def metrics_line(kp, frame, st):
    """A compact line with every metric — for working through each one."""
    kL, kR = M.knee_angles(kp)
    d = M.depth_margin(kp, frame)
    tr = M.trunk_incline(kp, frame, sagittal=True)
    ti = M.tibia_incline(kp, frame, sagittal=True)
    tt = M.trunk_tibia_angle(kp, frame)
    dom = M.squat_dominance(tt, DOMINANCE_CENTRE, DOMINANCE_BAND)
    vL = M.knee_medial_deviation(kp, frame, "L")
    vR = M.knee_medial_deviation(kp, frame, "R")
    sym = M.knee_symmetry(kp)
    sh = M.shoulder_tilt(kp, frame)
    def f(x, u="", nd=0):
        return f"{x:.{nd}f}{u}" if (x is not None and np.isfinite(x)) else "  -"
    return (f"[{st['phase']:7s} rep{st['rep_count']}] "
            f"knee {f(kL)}/{f(kR)}  pelH {f(st['pelvis_h'],'mm')} vP {f(st['pelvis_v'],'mm/s')} | "
            f"depth {f(d,'mm')}({_cls(d)})  trunk {f(tr,'d')} tibia {f(ti,'d')} "
            f"T-T {f(tt,'d')}({dom}) | valgus L{f(vL)} R{f(vR)}  "
            f"kneeSym {f(sym,'d')} shTilt {f(sh,'d')}")


def _cls(d):
    from rep_engine import classify_depth
    return classify_depth(d)

def rep_block(r):
    print("\n" + "=" * 70)
    print(f"REP {r['rep']}")
    print("=" * 70)

    print(
        f"DEPTH: target={r['target_depth']} | "
        f"performed={r['variation']} | "
        f"met={r['depth_met']}"
    )

    print(
        f"  depth margin: {r['depth_margin_mm']} mm | "
        f"knee angle: {r['knee_at_depth']} deg"
    )

    print(
        f"KNEE ALIGNMENT: {'VALGUS' if r['valgus'] else 'ok'} "
        f"(peak {r['valgus_dev_mm']} mm, held {r['valgus_s']}s "
        f"= {(r['valgus_frac'] or 0) * 100:.0f}% of the rep)"
    )

    print(
        f"SYMMETRY: knee={r['symmetry_deg']} deg | "
        f"shoulder tilt={r['shoulder_tilt_deg']} deg"
    )

    print(f"STRATEGY: T-T={r['trunk_tibia_deg']} deg ({r['dominance']})")

    print(
        f"TIMING: descent={r['descent_s']} s | "
        f"ascent={r['ascent_s']} s | "
        f"dwell={r['bottom_dwell_s']} s"
    )

    print(
        f"TRACES: depth={len(r['depth_traj'])} pts | "
        f"symmetry={len(r['symmetry_traj'])} | "
        f"shoulder={len(r['shoulder_tilt_traj'])}"
    )

    print(f"\nFAULTS: {r['faults']}")

    print("FEEDBACK:")
    if r["cues"]:
        for cue in r["cues"]:
            print(f"  - {cue}")
    else:
        print("  - none")

    print("=" * 70 + "\n")


CALIB_FILES = ("calib/extrinsics.json", "calib/vertical.json",
               "calib/cam0_intrinsics.json", "calib/cam1_intrinsics.json",
               "calib/cam2_intrinsics.json")


def calibration_fingerprint():
    """Identify the calibration a recording was made under, since a recording stores only triangulated 3D joints."""
    fp = {}
    for path in CALIB_FILES:
        if os.path.exists(path):
            with open(path, "rb") as fh:
                fp[os.path.basename(path)] = hashlib.md5(fh.read()).hexdigest()[:12]
    try:
        d = json.load(open("calib/extrinsics.json"))["cameras"]
        cent = {}
        for k, v in d.items():
            R = np.array(v["R"], float); t = np.array(v["t"], float).reshape(3, 1)
            cent[k] = (-R.T @ t).ravel()
        fp["baselines_mm"] = {f"{a}-{b}": round(float(np.linalg.norm(cent[a] - cent[b])), 1)
                              for i, a in enumerate(sorted(cent)) for b in sorted(cent)[i + 1:]}
    except Exception:
        pass
    try:
        fp["up"] = json.load(open("calib/vertical.json"))["up"]
    except Exception:
        pass
    return fp


def target_from_label(label, default):
    """Take the assessment target from the set label, so a set labelled 'deep' is assessed as deep."""
    low = label.lower()
    for t in ("partial", "parallel", "deep"):
        if t in low:
            return t
    return default


def stance_guard(kp, frame, shoulder_mm):
    """One line naming the stance width and whether it is in the medium band."""
    r = M.stance_width_ratio(kp, frame, shoulder_mm=shoulder_mm)
    if not np.isfinite(r):
        return "stance: not measurable"
    cls, _ = M.classify_stance_width(r)
    flag = "" if cls == "medium" else "   <<< OUTSIDE THE MEDIUM BAND - WIDEN/NARROW BEFORE THIS SET"
    return f"stance: {r:.2f}x shoulder width ({cls}){flag}"


def _send_setup(stream, kp, t, countdown=None, cams=None, refs_ready=None):
    """Push one pre-set frame to Unity so the avatar stays live between the calibration and the first rep."""
    if stream is None or kp is None or t is None:
        return
    try:
        stream.send(kp, t, {"phase": "SETUP", "rep_count": 0,
                            "countdown": countdown,
                            "refs_ready": refs_ready,
                            "cams": stream._cam_counts(_LAST_CONF, cams)})
    except Exception:
        pass


def wait_for_start(ctl, model, caps, order, indices, rig, kalman, device, prev,
                   tw, no_video, stream, eng=None):
    """Idle until the athlete presses Start in Unity, streaming the whole time and feeding the engine's knee-gap baseline."""
    said = False
    while True:
        if ctl.take_start():
            ctl.take_end()
            return prev, True
        sm3d, frames, valid, t, dt = grab(model, caps, order, indices, rig,
                                          kalman, device, prev)
        prev = t
        if eng is not None and sm3d is not None and t is not None:
            eng.seed_stance(sm3d, t)
        _send_setup(stream, sm3d, t, cams=indices,
                    refs_ready=eng.references_ready() if eng is not None else None)
        if not said:
            print("\nWaiting for Start in Unity...")
            said = True
        if not no_video and frames is not None:
            if show(frames, valid, indices, rig, sm3d, tw,
                    banner="press Start in Unity") == ord("q"):
                return prev, False


def wait_for_stance(model, caps, order, indices, rig, kalman, device, prev,
                    tw, no_video, frame, shoulder_mm, hold_s, msg, stream=None):
    """Block until the athlete is standing in a medium stance and has held it for `hold_s` seconds."""
    held, last_note, t_prev, step = 0.0, None, None, 0.0
    quiet_since = time.time()
    while True:
        sm3d, frames, valid, t, dt = grab(model, caps, order, indices, rig,
                                          kalman, device, prev)
        prev = t
        if t is not None:
            step = (t - t_prev) if t_prev is not None else 0.0
            t_prev = t

        _send_setup(stream, sm3d, t, cams=indices)

        ok_now = False
        if sm3d is None:
            if time.time() - quiet_since > 3.0:
                print("  waiting for a person in view...")
                quiet_since = time.time()
        if sm3d is not None:
            quiet_since = time.time()
            kp = np.asarray(sm3d, float)
            r = M.stance_width_ratio(kp, frame, shoulder_mm=shoulder_mm)
            cls, _ = M.classify_stance_width(r)
            ok_now = cls == "medium"
            note = stance_guard(kp, frame, shoulder_mm)
            if note != last_note:
                print("  " + note)
                last_note = note

        held = held + step if (ok_now and t is not None) else 0.0
        if held >= hold_s:
            return prev, True

        if not no_video and frames is not None:
            bar = int(20 * min(held / hold_s, 1.0)) if hold_s > 0 else 20
            banner = (f"{msg}  hold the stance  [{'#' * bar}{'.' * (20 - bar)}]"
                      if ok_now else f"{msg}  stand in a medium stance")
            if show(frames, valid, indices, rig, sm3d, tw, banner=banner) == ord("q"):
                return prev, False


def run_countdown(secs, model, caps, order, indices, rig, kalman, device, prev,
                  tw, no_video, msg, frame=None, shoulder_mm=None, eng=None, rec=None,
                  stream=None):
    t0 = time.time(); shown = None
    said = False
    def _more():
        el = time.time() - t0
        if el < secs:
            return True
        return (eng is not None and not no_video and el < secs + 10.0
                and not eng.references_ready())
    while _more():
        rem = int(secs - (time.time() - t0)) + 1
        if no_video:
            if rem != shown:
                print(f"  {msg} in {rem}..."); shown = rem
            time.sleep(0.05)
        else:
            sm3d, frames, valid, t, dt = grab(model, caps, order, indices, rig,
                                              kalman, device, prev)
            prev = t
            if rec is not None and t is not None:
                rec.add(sm3d, t, raw=_LAST_RAW, pts=_LAST_PTS, conf=_LAST_CONF)
            if eng is not None and sm3d is not None and t is not None:
                eng.seed_stance(sm3d, t)
            _send_setup(stream, sm3d, t, countdown=max(rem, 1), cams=indices,
                        refs_ready=eng.references_ready() if eng is not None else None)
            if frames is not None:
                show(frames, valid, indices, rig, sm3d, tw,
                     banner=f"{msg}  {rem}" if rem > 0 else f"{msg}  stand still and upright")
            if (not said and frame is not None and sm3d is not None
                    and rem <= max(1, int(secs) - 2)):
                print("  " + stance_guard(np.asarray(sm3d, float), frame, shoulder_mm))
                said = True
    if eng is not None and not eng.references_ready():
        print("!! references still missing after the count-in - this set's "
              "valgus/depth may be unmeasured.")
    return prev


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("indices", nargs="+", type=int)
    ap.add_argument("--target", default="parallel", choices=["partial", "parallel", "deep"])
    ap.add_argument("--calib-seconds", type=float, default=2.0)
    ap.add_argument("--tile", type=int, default=640,
                    help="per-camera width in px (bigger = larger window; try 800)")
    ap.add_argument("--no-video", action="store_true")
    ap.add_argument("--clean-video", action="store_true",
                    help="camera windows without the skeleton, labels or banners (for screen recordings)")
    ap.add_argument("--show-cam", type=int, nargs="+", default=None, metavar="CAM",
                    help="open windows only for these camera indices, e.g. --show-cam 1")
    ap.add_argument("--countdown", type=float, default=10.0,
                    help="seconds to count down after SPACE before calibrating")
    ap.add_argument("--person-up", action="store_true",
                    help="force the standing-person vertical even if calib/vertical.json exists")
    ap.add_argument("--record", metavar="DIR", default=None,
                    help="record each set to DIR/<session>/NN_<label>.npz; a label is asked for before each set")
    ap.add_argument("--session", default=None,
                    help="session folder name (default: timestamp)")
    ap.add_argument("--notes", default="", help="free-text note stored in every set's meta")
    ap.add_argument("--set-dump", default="results/sets", metavar="DIR",
                    help="write each set's per-repetition results to DIR/<session>/NN_<label>.json")
    ap.add_argument("--no-report", action="store_true",
                    help="skip the HTML report; the set dumps are still written")
    ap.add_argument("--no-set-dump", action="store_true",
                    help="do not write the per-set assessment files")
    ap.add_argument("--no-undistort", action="store_true",
                    help="triangulate without lens-distortion correction (for comparison only)")
    ap.add_argument("--timing", action="store_true",
                    help="write the time spent in each pipeline stage per frame to a CSV and print a summary")
    ap.add_argument("--timing-file", default=None,
                    help="where the timing CSV goes (default "
                         "results/timing_<session>.csv)")
    ap.add_argument("--set-countdown", type=float, default=6.0,
                    help="terminal-driven capture only: seconds from stance hold to set start (at least 4)")
    ap.add_argument("--stance-hold", type=float, default=1.0,
                    help="terminal-driven capture only: seconds the medium stance must be held; 0 disables")
    ap.add_argument("--no-stance-gate", action="store_true",
                    help="terminal-driven capture only: start the countdown without waiting for a medium stance")
    ap.add_argument("--drain", action="store_true",
                    help="discard stale frames from each camera queue every loop")
    ap.add_argument("--drain-mode", default="formula", choices=["formula", "edge"],
                    help="how --drain chooses frames to discard")
    ap.add_argument("--edge-ms", type=float, default=8.0,
                    help="a grab faster than this had a frame already waiting")
    ap.add_argument("--cam-fps", type=float, default=30.0,
                    help="the cameras' free-running rate, used to size the flush")
    ap.add_argument("--filter", default="euro", choices=["euro", "kalman", "none"],
                    help="3D smoothing filter for the measurements")
    ap.add_argument("--euro-min-cutoff", type=float, default=1.0,
                    help="One Euro cutoff (Hz) as speed -> 0. Lower = smoother "
                         "when the athlete is still")
    ap.add_argument("--euro-beta", type=float, default=0.020,
                    help="One Euro speed coefficient (1/mm). Higher = opens up "
                         "faster when moving, so less lag on a fast descent")
    ap.add_argument("--display-min-cutoff", type=float, default=0.5,
                    help="One Euro cutoff for the avatar stream only")
    ap.add_argument("--display-beta", type=float, default=0.002,
                    help="One Euro speed coefficient for the avatar stream only")
    ap.add_argument("--no-display-filter", action="store_true",
                    help="send the measurement stream to Unity unchanged, "
                         "instead of a separately smoothed display stream")
    ap.add_argument("--process-var", type=float, default=12.0,
                    help="Kalman process variance (--filter kalman only)")
    ap.add_argument("--measurement-var", type=float, default=4.0,
                    help="Kalman measurement variance in mm^2 (--filter kalman only)")
    ap.add_argument("--save-video", action="store_true",
                    help="also save each recorded set's camera frames as video (needs --record)")
    ap.add_argument("--video-fps", type=float, default=10.0,
                    help="nominal fps in the .avi header; true frame times are "
                         "saved alongside and are what alignment must use")
    ap.add_argument("--stream", action="store_true",
                    help="also stream live poses to Unity over UDP")
    ap.add_argument("--unity-setup", action="store_true",
                    help="stream the skeleton to Unity during calibration")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5006)
    ap.add_argument("--control-port", type=int, default=5007)
    ap.add_argument("--no-mirror", action="store_true",
                    help="show the avatar as a partner facing you (true anatomy) "
                         "instead of the default gym-mirror view")
    ap.add_argument("--no-control", action="store_true")
    ap.add_argument("--diagnostic", action="store_true",
                    help="print per-frame metrics and state-machine transitions")
    a = ap.parse_args()
    global CLEAN_VIDEO, SHOW_CAMS
    CLEAN_VIDEO = a.clean_video
    SHOW_CAMS = set(a.show_cam) if a.show_cam else None
    indices = a.indices
    tw = a.tile
    fixed_up = None if a.person_up else load_fixed_up()

    rig = load_rig(indices)
    device = pick_device()
    print(f"Loading YOLO11n-pose on {device} ...")
    model = YOLO("yolo11n-pose.pt")
    caps = {}
    for i in indices:
        cap = open_camera(i)
        if cap is not None:
            caps[i] = cap
        else:
            print(f"cam{i} did not open.")
    if len(caps) < 2:
        print("Need at least 2 cameras."); return
    order = [i for i in indices if i in caps]
    OPT["drain"], OPT["cam_fps"] = a.drain, a.cam_fps
    OPT["drain_mode"], OPT["edge_ms"] = a.drain_mode, a.edge_ms
    OPT["undistort"] = not a.no_undistort
    print("Lens distortion: " + ("corrected before triangulation"
                                 if OPT["undistort"] else "NOT corrected (--no-undistort)"))
    if a.drain:
        mode = ("to the live edge" if a.drain_mode == "edge"
                else f"by formula, cameras assumed {a.cam_fps:.0f} fps")
        print(f"Camera queue flushing ON ({mode}).")
    global _DISPLAY_FILTER
    if not a.no_display_filter:
        _DISPLAY_FILTER = SkeletonOneEuro(min_cutoff=a.display_min_cutoff,
                                          beta=a.display_beta)
        print(f"Avatar smoothing: One Euro "
              f"({a.display_min_cutoff}, {a.display_beta}) — display only, "
              f"the reported metrics do not pass through it.")
    if a.filter == "euro":
        kalman = SkeletonOneEuro(min_cutoff=a.euro_min_cutoff, beta=a.euro_beta)
        print(f"Smoothing: One Euro (min_cutoff={a.euro_min_cutoff}, "
              f"beta={a.euro_beta}).")
    elif a.filter == "kalman":
        kalman = SkeletonKalman(process_var=a.process_var,
                                measurement_var=a.measurement_var)
        print(f"Smoothing: constant-velocity Kalman (q={a.process_var}, "
              f"r={a.measurement_var}) — expect ~347 ms of group delay.")
    else:
        kalman = PassThrough()
        print("Smoothing: NONE, raw triangulation.")

    prev = None
    src = "rig vertical (calib/vertical.json)" if fixed_up is not None else "standing person's axis"
    print(f"\nVertical reference: {src}."
          + ("" if fixed_up is not None else
             "  (run calibrate_vertical.py with the board on the floor for a true rig vertical)"))

    setup_stream = None
    if a.stream and a.unity_setup:
        from pose_to_unity import PoseStreamer as _PS
        setup_stream = _PS(None, a.host, a.port, mirror=not a.no_mirror,
                           target=a.target)
        print(f"Unity setup view ON -> pre-calibration skeleton to "
              f"{a.host}:{a.port}.")

    early_ctl = None
    if setup_stream is not None and not a.no_control:
        from control_listener import ControlListener
        early_ctl = ControlListener(port=a.control_port, target=a.target).start()

    def _unity_go():
        """True once Enter has been pressed on Unity's pre-calibration screen."""
        return early_ctl is not None and early_ctl.take_calibrate()

    def _setup_push(kp3d, tt, countdown=None, note=None, awaiting=False):
        """Best-effort: the setup view must never be able to stop a session."""
        if setup_stream is None or tt is None:
            return
        try:
            setup_stream.send_setup_pose(kp3d, tt, up=fixed_up, conf=_LAST_CONF,
                                         cams=indices, countdown=countdown,
                                         note=note, awaiting=awaiting)
        except Exception:
            pass

    fail_note = None
    while True:
        sm3d = None
        if a.no_video and setup_stream is None:
            input("Stand in the volume in front of the cameras, then press Enter to calibrate...")
        elif a.no_video:
            import select
            print("Press Enter here or in Unity to start the countdown, then walk "
                  "into the camera volume.")
            while True:
                sm3d, frames, valid, t, dt = grab(model, caps, order, indices, rig,
                                                  kalman, device, prev)
                prev = t
                _setup_push(sm3d, t, awaiting=True, note=fail_note)
                if _unity_go():
                    break
                if select.select([sys.stdin], [], [], 0)[0]:
                    sys.stdin.readline()
                    break
        else:
            print("Press SPACE (or Enter in Unity) to start the countdown (q quits).")
            while True:
                sm3d, frames, valid, t, dt = grab(model, caps, order, indices, rig, kalman, device, prev)
                prev = t
                if _unity_go():
                    break
                if frames is None:
                    continue
                _setup_push(sm3d, t, awaiting=True, note=fail_note)
                key = show(frames, valid, indices, rig, sm3d, tw,
                           banner=(fail_note + "  SPACE retries") if fail_note
                           else "press SPACE when ready")
                if key == ord(" "):
                    break
                if key == ord("q"):
                    for c in caps.values():
                        c.release()
                    cv2.destroyAllWindows()
                    return

        if a.countdown > 0:
            c0, shown = time.time(), None
            while time.time() - c0 < a.countdown:
                rem = int(a.countdown - (time.time() - c0)) + 1
                if a.no_video and setup_stream is None:
                    if rem != shown:
                        print(f"  calibrating in {rem}...");  shown = rem
                    time.sleep(0.05)
                elif a.no_video:
                    sm3d, frames, valid, t, dt = grab(model, caps, order, indices, rig,
                                                      kalman, device, prev)
                    prev = t
                    _setup_push(sm3d, t, countdown=rem, note="get into position")
                    if rem != shown:
                        print(f"  calibrating in {rem}...");  shown = rem
                else:
                    sm3d, frames, valid, t, dt = grab(model, caps, order, indices, rig, kalman, device, prev)
                    prev = t
                    _setup_push(sm3d, t, countdown=rem, note="get into position")
                    if frames is not None:
                        show(frames, valid, indices, rig, sm3d, tw, banner=f"hold still  {rem}")

        fail_note = None
        sm3d, frames, valid, t, dt = grab(model, caps, order, indices, rig,
                                          kalman, device, prev)
        prev = t
        if not enough_joints(sm3d):
            fail_note = CALIB_FAIL["joints"]
            print(fail_note + " Press Enter to try again.")
            continue
        print(f"Hold still and upright for {a.calib_seconds:.0f}s ...")
        samples, n_cycles, t0 = [], 0, time.time()
        while time.time() - t0 < a.calib_seconds + 1.0:
            sm3d, frames, valid, t, dt = grab(model, caps, order, indices, rig, kalman, device, prev)
            prev = t
            n_cycles += 1
            if sm3d is None:
                continue
            samples.append((sm3d.copy(), enough_joints(sm3d) and enough_joints(_LAST_RAW)))
            _setup_push(sm3d, t, note="hold still")
            if not a.no_video:
                if show(frames, valid, indices, rig, sm3d, tw, banner="calibrating...") == ord("q"):
                    break
        stand, why = accept_calibration(samples, n_cycles)
        if why is not None:
            fail_note = CALIB_FAIL[why]
            print(f"{fail_note} ({len(samples)} frames over {n_cycles} cycles.) "
                  "Press Enter to try again.")
            continue
        print(f"Calibration accepted: {len(stand)} of {n_cycles} frames fresh, "
              f"upright and within {CALIB_STILL_MM:.0f} mm.")
        break
    frame = M.calibrate_body_frame(stand, fixed_up=fixed_up)
    print(f"Body frame set from {len(stand)} frames.  up = {np.round(frame.up,3)}  [{src}]")

    s0 = stand[-1]
    sw = M.stance_width_ratio(s0, frame)
    scls, scue = M.classify_stance_width(sw)
    print("Standing sanity (should be near-zero / symmetric if calibration is good):")
    print(f"   valgus L {M.knee_medial_deviation(s0,frame,'L'):.0f}mm  "
          f"R {M.knee_medial_deviation(s0,frame,'R'):.0f}mm   "
          f"shoulderTilt {M.shoulder_tilt(s0,frame):.0f}d   "
          f"stanceWidth {sw:.2f} ({scls})")
    if scue:
        print(f"   setup: {scue}")
    print("   (a persistent one-sided valgus while standing normally = calibration bias, not your knee)\n")

    theta0 = float(np.nanmean([M.knee_signal(s) for s in stand]))
    h0 = float(np.nanmean([M.pelvis_height(s, frame) for s in stand]))
    print(f"Baseline: knee {theta0:.0f}deg  pelvis {h0:.0f}mm")
    from rep_engine import valgus_neutral
    valgus0, v0_note = valgus_neutral(stand, frame)
    print(f"Knee neutral: {v0_note}")
    calib_femur = calibration_femur(stand)
    print(f"Femur {calib_femur:.0f} mm (median of {len(stand)} calibration frames), "
          "fixed until the next calibration.")

    ctl = stream = None

    from pose_to_unity import PoseStreamer
    subject_mm = PoseStreamer.subject_hip_ankle(stand)
    shoulder_mm = PoseStreamer.subject_shoulder_width(stand, frame)
    if shoulder_mm:
        print(f"Shoulder width: {shoulder_mm:.0f} mm "
              f"(fixed denominator for the stance check; foot targets "
              f"{shoulder_mm * 1.25:.0f} mm apart).")
    from pose_to_unity import limb_lengths as _ll
    _lm = _ll(stand)
    print(f"CALIB  shoulder {shoulder_mm or float('nan'):.0f} mm | "
          f"hip-ankle {subject_mm or float('nan'):.0f} mm | "
          f"femur L {_lm.get('left_hip', float('nan')):.0f} R {_lm.get('right_hip', float('nan')):.0f} mm | "
          f"shank L {_lm.get('left_knee', float('nan')):.0f} R {_lm.get('right_knee', float('nan')):.0f} mm "
          f"({len(stand)} frames)")

    if a.stream:
        try:
            origin = PoseStreamer.floor_origin(stand, frame)
            from pose_to_unity import limb_lengths
            if setup_stream is not None:
                stream = setup_stream
                stream.calibrate(frame, origin=origin, subject_mm=subject_mm,
                                 shoulder_mm=shoulder_mm,
                                 limb_mm=limb_lengths(stand))
                stream.target = a.target
            else:
                stream = PoseStreamer(frame, a.host, a.port, origin=origin,
                                      target=a.target, subject_mm=subject_mm,
                                      shoulder_mm=shoulder_mm,
                                      mirror=not a.no_mirror,
                                      limb_mm=limb_lengths(stand))
            print("Avatar view: " + ("gym mirror (your right stays on your right)"
                                     if not a.no_mirror else
                                     "facing partner (true anatomy, not mirrored)"))
            if subject_mm:
                print(f"Subject hip-to-ankle: {subject_mm:.0f} mm "
                      f"(avatar scaled to this once, then frozen).")
            print(f"Streaming to {a.host}:{a.port} — press Play in Unity.")
            if not a.no_control:
                from control_listener import ControlListener
                ctl = early_ctl or ControlListener(port=a.control_port,
                                                   target=a.target).start()
                ctl.take_start()
        except Exception as exc:
            print(f"!! streaming disabled: {exc}")
            stream = ctl = None

    calib_fp = calibration_fingerprint()
    session_id = a.session or time.strftime("%Y%m%d_%H%M%S")
    global TIMER
    if a.timing:
        tpath = a.timing_file or os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "results", f"timing_{session_id}.csv")
        TIMER = StageTimer(tpath)
        print(f"Stage timing ON -> {tpath}")
    outdir = None
    if a.record:
        outdir = os.path.join(a.record, session_id)
        os.makedirs(outdir, exist_ok=True)
        print(f"\nRECORDING to {outdir}/")
        print("  You will be asked for a label before each set (e.g. parallel, deep,")
        print("  partial, valgus_in, valgus_out, normal). A label containing")
        print("  partial/parallel/deep also sets the assessment target for that set.")
        print("  Press q in the video window to END A SET; blank label to finish.\n")

    set_idx = 0
    pending_start = False
    set_reports = []
    try:
        while True:
            label, rec, tgt, vid = None, None, a.target, None
            eng = SquatRepEngine(frame, target=tgt, theta0=theta0, h0=h0,
                                 stance_kp=stand[-1], shoulder_mm=shoulder_mm,
                                 femur_mm=calib_femur)
            if not a.record and ctl is not None:
                if pending_start:
                    pending_start = False
                else:
                    prev, ok = wait_for_start(ctl, model, caps, order, indices, rig,
                                              kalman, device, prev, tw, a.no_video,
                                              stream, eng=eng)
                    if not ok:
                        break
                set_idx += 1
                tgt = ctl.target
                print(f"--- SET {set_idx}  (assessed as {tgt}).  Go!")
                print(f"    {eng.gap_note}")
                print(f"    {eng.femur_note}")
            if a.record:
                try:
                    label = input("Label for the next set (blank = finish): ").strip()
                except EOFError:
                    label = ""
                if not label:
                    break
                set_idx += 1
                tgt = target_from_label(label, a.target)
                safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in label)
                path = os.path.join(outdir, f"{set_idx:02d}_{safe}.npz")
                rec = SessionRecorder(path, meta={
                    "body_frame": meta_from_body_frame(frame),
                    "label": label, "target": tgt, "set_index": set_idx,
                    "session_id": session_id, "notes": a.notes,
                    "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "calibration": calib_fp,
                    "theta0_deg": theta0, "h0_mm": h0,
                    "calib_stand_gap_mm": valgus0,
                    "cameras": order, "vertical_source": src,
                })
            eng.target = tgt

            if a.record:
                if not a.no_stance_gate and a.stance_hold > 0:
                    prev, ok = wait_for_stance(model, caps, order, indices, rig,
                                               kalman, device, prev, tw, a.no_video,
                                               frame, shoulder_mm, a.stance_hold,
                                               f"SET {set_idx}"
                                               + (f" [{label}]" if label else ""),
                                               stream=stream)
                    if not ok:
                        print("--- quit at the stance gate; finishing the session.")
                        break
                prev = run_countdown(a.set_countdown, model, caps, order, indices, rig,
                                     kalman, device, prev, tw, a.no_video,
                                     f"SET {set_idx}"
                                     + (f" [{label}]" if label else "") + " starts",
                                     frame=frame, shoulder_mm=shoulder_mm,
                                     eng=eng, rec=rec, stream=stream)
                if rec is not None:
                    rec.meta["set_start_index"] = len(rec)
                    if a.save_video:
                        vid = SetVideoWriter(outdir, f"{set_idx:02d}_{safe}", order,
                                             fps=a.video_fps)
                    print(f"--- SET {set_idx}: {label}  (assessed as {tgt})  RECORDING. q ends the set.")
                    print(f"    {eng.gap_note}")
                    print(f"    {eng.femur_note}")
            if stream is not None:
                stream.target = tgt
            if not a.record and ctl is None:
                print(f"Target depth = {tgt}.  Go! (q or Ctrl-C to stop)\n")
            last_print, last_live_cue, last_phase = 0.0, None, None
            set_depths, set_reports = [], []
            if TIMER is not None:
                TIMER.new_set()

            while True:
                sm3d, frames, valid, t, dt = grab(model, caps, order, indices, rig,
                                                  kalman, device, prev)
                prev = t
                if rec is not None and t is not None:
                    rec.add(sm3d, t, raw=_LAST_RAW, pts=_LAST_PTS, conf=_LAST_CONF)
                if vid is not None and frames is not None and t is not None:
                    vid.add(frames, valid, t)
                if sm3d is None:
                    if not a.no_video and frames is not None:
                        if show(frames, valid, indices, rig, sm3d, tw) == ord("q"):
                            break
                    continue
                if ctl is not None and ctl.take_end():
                    print("--- set closed by Unity (rep target reached).")
                    break
                if ctl is not None and not a.record and ctl.take_start():
                    pending_start = True
                    break
                if ctl is not None and ctl.take():
                    eng.target = ctl.target
                    if stream is not None:
                        stream.target = ctl.target
                    print(f"\n>>> target is now {ctl.target}")
                _ta = time.perf_counter()
                st = eng.update(sm3d, t)
                if TIMER is not None:
                    TIMER.mark("assess", time.perf_counter() - _ta)
                rep_blk = st["last_rep"] if st["rep_completed"] else None
                _ts = time.perf_counter()
                if stream is not None:
                    try:
                        stream.send(_LAST_DISPLAY if _LAST_DISPLAY is not None
                                    else sm3d, t, st, rep_blk, measure_kp=sm3d)
                    except Exception:
                        pass
                if TIMER is not None:
                    TIMER.mark("send", time.perf_counter() - _ts)
                if a.diagnostic and st["phase"] != last_phase:
                    print(f"\n>>> PHASE: {last_phase} -> {st['phase']} "
                          f"| knee={st['knee_angle']} | pelvis={st['pelvis_h']} "
                          f"| velocity={st['pelvis_v']}")
                    last_phase = st["phase"]
                if a.diagnostic and t - last_print > 0.5:
                    print(metrics_line(sm3d, frame, st))
                    last_print = t
                if a.diagnostic and st["live_cue"] != last_live_cue:
                    if st["live_cue"]:
                        print("   LIVE:", st["live_cue"])
                    last_live_cue = st["live_cue"]
                if st.get("rep_abandoned"):
                    print("!! tracking lost for over "
                          f"{REP_ABANDON_S:.1f} s mid-rep - that rep was abandoned, not assessed.")
                if st["rep_completed"]:
                    rep_block(st["last_rep"])
                    if not np.isfinite(st["last_rep"].get("knee_gap_mm", np.nan)):
                        print("!! VALGUS NOT REFERENCED - no steady standing frames "
                              "before this set, so the knee check did not run. "
                              "Stand still in your stance for ~2 s before the first rep.")
                    set_depths.append(st["last_rep"].get("depth_margin_mm"))
                    set_reports.append(st["last_rep"])
                _td = time.perf_counter()
                key = show(frames, valid, indices, rig, sm3d, tw) if not a.no_video else -1
                if TIMER is not None:
                    TIMER.mark("draw", time.perf_counter() - _td)
                    TIMER.commit(t, len(frames) if frames is not None else 0,
                                 int(sm3d is not None))
                if key == ord("q"):
                    break

            if not a.no_set_dump:
                try:
                    dumped = write_set(
                        os.path.join(a.set_dump, session_id), set_reports,
                        session_id=session_id, set_index=set_idx, target=tgt,
                        label=label, engine=eng, theta0_deg=theta0, h0_mm=h0,
                        calibration=calib_fp, notes=a.notes, options=vars(a),
                        driver="unity" if ctl is not None else "terminal")
                    if dumped:
                        print(f"--- set assessments -> {dumped}  ({len(set_reports)} reps)")
                        if not a.no_report:
                            refresh_report(os.path.join(a.set_dump, session_id))
                    set_reports = []
                except Exception as exc:
                    print(f"!! could not write the set assessments: {exc}")
            if vid is not None:
                vstats = vid.close()
                print(f"--- video: {vstats['written']} frames/cam, "
                      f"{vstats['dropped']} dropped")
                if rec is not None:
                    rec.meta["video"] = vstats
            if rec is not None:
                rec.meta["reps_detected"] = eng.rep_count
                rec.meta["reps_abandoned"] = eng.abandoned_reps
                rec.meta["n_frames"] = len(rec)
                saved = rec.save()
                if saved:
                    kb = os.path.getsize(saved) / 1024.0
                    print(f"--- saved {saved}  ({len(rec)} frames, "
                          f"{eng.rep_count} reps, {kb:.0f} kB)")
                    depths = [d for d in set_depths
                              if d is not None and np.isfinite(d)]
                    if depths:
                        print(f"--- bottom depth this set: median {np.median(depths):.0f} mm, "
                              f"range {min(depths):.0f}..{max(depths):.0f} "
                              f"(spread {max(depths) - min(depths):.0f} mm)")
                    print()
                else:
                    print("--- nothing recorded for that set (no frames).\n")
            if not a.record and ctl is None:
                break
    except KeyboardInterrupt:
        try:
            if not a.no_set_dump and set_reports:
                dumped = write_set(
                    os.path.join(a.set_dump, session_id), set_reports,
                    session_id=session_id, set_index=set_idx, target=tgt,
                    label=label, engine=eng, theta0_deg=theta0, h0_mm=h0,
                    calibration=calib_fp, notes=a.notes, options=vars(a),
                    driver="unity" if ctl is not None else "terminal")
                if dumped:
                    print(f"--- interrupted: set assessments -> {dumped} ({len(set_reports)} reps)")
                set_reports = []
            if rec is not None and len(rec):
                rec.meta["reps_detected"] = eng.rep_count
                rec.meta["n_frames"] = len(rec)
                saved = rec.save()
                if saved:
                    print(f"--- interrupted: saved {saved} ({len(rec)} frames)")
        except Exception as exc:
            print(f"!! could not flush the interrupted set: {exc}")
    finally:
        if not a.no_set_dump and not a.no_report:
            _rpt = refresh_report(os.path.join(a.set_dump, session_id), quiet=True)
            if _rpt:
                print(f"\nReport: file://{os.path.abspath(_rpt)}")
        SetVideoWriter.close_all()
        for c in caps.values():
            c.release()
        cv2.destroyAllWindows()
        if TIMER is not None:
            report = TIMER.close()
            print(report)
            try:
                with open(TIMER.path.replace(".csv", ".txt"), "w") as fh:
                    fh.write(report + "\n")
            except Exception:
                pass
        if a.record and outdir:
            print(f"\nSession {session_id}: {set_idx} set(s) in {outdir}/")
            print("Back this folder up NOW, and check it today while the rig stands.")


if __name__ == "__main__":
    main()
