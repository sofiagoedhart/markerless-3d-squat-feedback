"""Turn a 3D skeleton into segment orientations and stream them to Unity over UDP."""
from __future__ import annotations

import json
import socket
import numpy as np

L_EYE, R_EYE = 1, 2
L_EAR, R_EAR = 3, 4

import metrics as M

MM_TO_M = 0.001

STANCE_NARROW, STANCE_WIDE = 1.0, 1.5

CUE_SHORT = {
    "valgus":        "Knees moving inward",
    "shoulder_tilt": "Shoulders are uneven",
    "shallow":       "Not deep enough",
    "good":          "Good rep",
    "depth_unmeasured": "Can't see you properly",
}


def _cue_key(text):
    """Map a cue sentence back to the fault name that produced it."""
    from rep_engine import CUES, DEPTH_CUES
    if not text:
        return None
    for k, v in CUES.items():
        if v == text:
            return k
    for k, v in DEPTH_CUES.items():
        if v == text:
            return k.split("_")[-1]
    return None

L_ELB, R_ELB = 7, 8
L_WRI, R_WRI = 9, 10

SEGMENT_ORDER = [
    "pelvis",
    "spine1",
    "left_hip", "left_knee", "left_ankle",
    "right_hip", "right_knee", "right_ankle",
    "neck",
    "left_shoulder", "left_elbow",
    "right_shoulder", "right_elbow",
]

MIRROR_IDX = [0, 2, 1, 4, 3, 6, 5, 8, 7, 10, 9, 12, 11, 14, 13, 16, 15]


def mirror_kp(kp, frame: M.BodyFrame, origin=None):
    """Reflect a skeleton in the sagittal plane through `origin` and swap left for right, so the avatar reads as a gym mirror."""
    kp = np.asarray(kp, float)
    lat = np.asarray(frame.lateral, float)
    o = (np.asarray(origin, float) if origin is not None
         else M._mid(kp[M.L_HIP], kp[M.R_HIP]))
    if not np.all(np.isfinite(o)):
        return kp
    d = (kp - o) @ lat
    return (kp - 2.0 * d[:, None] * lat)[MIRROR_IDX]


def _unit(v):
    v = np.asarray(v, float)
    n = np.linalg.norm(v)
    return v / n if n > 1e-9 else None


def _dir(kp, a, b):
    """Unit vector from joint a to joint b, or None if either is missing."""
    if not (np.all(np.isfinite(kp[a])) and np.all(np.isfinite(kp[b]))):
        return None
    return _unit(kp[b] - kp[a])


def to_unity_vec(v, frame: M.BodyFrame):
    """World vector (any units) -> Unity axes (X=subject right, Y=up, Z=forward)."""
    v = np.asarray(v, float)
    return np.array([-float(np.dot(v, frame.lateral)),
                     float(np.dot(v, frame.up)),
                     float(np.dot(v, frame.forward))])


def setup_frame(kp, up=None):
    """A provisional body frame for the setup view: the rig vertical for up (or the athlete's own ankle-to-shoulder axis if there is none) and her shoulder line for lateral."""
    kp = np.asarray(kp, float)
    mank = M._mid(kp[M.L_ANK], kp[M.R_ANK])
    msho = M._mid(kp[M.L_SHO], kp[M.R_SHO])
    if up is None:
        up = (msho - mank if np.all(np.isfinite(mank)) and np.all(np.isfinite(msho))
              else np.array([0.0, 1.0, 0.0]))
    up = _unit(np.asarray(up, float))
    lat, sL, sR = None, kp[M.L_SHO], kp[M.R_SHO]
    if np.all(np.isfinite(sL)) and np.all(np.isfinite(sR)):
        v = (sL - sR) - np.dot(sL - sR, up) * up
        if np.linalg.norm(v) > 1e-6:
            lat = _unit(v)
    if lat is None:
        seed = np.array([1.0, 0.0, 0.0])
        if abs(float(np.dot(seed, up))) > 0.9:
            seed = np.array([0.0, 1.0, 0.0])
        lat = _unit(seed - np.dot(seed, up) * up)
    return M.BodyFrame(up=up, lateral=lat, forward=_unit(np.cross(up, lat)))


def to_unity_point(p, frame: M.BodyFrame, origin=None):
    """World point in mm -> Unity metres, relative to `origin` (world mm)."""
    p = np.asarray(p, float)
    if origin is not None:
        p = p - np.asarray(origin, float)
    return to_unity_vec(p, frame) * MM_TO_M


def basis_from(long_v, ref_v, fallback_ref=None):
    """Gram-Schmidt an orthonormal basis from a longitudinal and a reference axis."""
    e1 = _unit(long_v)
    if e1 is None:
        return None
    for cand in (ref_v, fallback_ref):
        if cand is None:
            continue
        r = np.asarray(cand, float)
        r = r - np.dot(r, e1) * e1
        e2 = _unit(r)
        if e2 is not None and np.linalg.norm(r) > 0.15:
            return e1, e2, np.cross(e1, e2)
    return None


def basis_to_quat(e1, e2, e3):
    """(e_long, e_ref, e_third) -> quaternion (x, y, z, w)."""
    R = np.column_stack([e1, e2, e3])
    tr = np.trace(R)
    if tr > 0:
        s = np.sqrt(tr + 1.0) * 2
        w = 0.25 * s
        x = (R[2, 1] - R[1, 2]) / s
        y = (R[0, 2] - R[2, 0]) / s
        z = (R[1, 0] - R[0, 1]) / s
    else:
        i = int(np.argmax(np.diag(R)))
        j, k = (i + 1) % 3, (i + 2) % 3
        s = np.sqrt(1.0 + R[i, i] - R[j, j] - R[k, k]) * 2
        q = np.zeros(3)
        q[i] = 0.25 * s
        q[j] = (R[j, i] + R[i, j]) / s
        q[k] = (R[k, i] + R[i, k]) / s
        w = (R[k, j] - R[j, k]) / s
        x, y, z = q
    return np.array([x, y, z, w])


LIMB_PAIRS = {
    "left_shoulder": (M.L_SHO, L_ELB), "left_elbow": (L_ELB, L_WRI),
    "right_shoulder": (M.R_SHO, R_ELB), "right_elbow": (R_ELB, R_WRI),
    "left_hip": (M.L_HIP, M.L_KNE), "left_knee": (M.L_KNE, M.L_ANK),
    "right_hip": (M.R_HIP, M.R_KNE), "right_knee": (M.R_KNE, M.R_ANK),
}


def limb_lengths(standing_skeletons) -> dict:
    """Median length of each driven bone over the standing calibration, in mm."""
    out = {}
    for name, (a, b) in LIMB_PAIRS.items():
        d = [float(np.linalg.norm(kp[b] - kp[a])) for kp in standing_skeletons
             if np.all(np.isfinite(kp[a])) and np.all(np.isfinite(kp[b]))]
        if len(d) >= 5:
            out[name] = float(np.median(d))
    return out


def segment_axes(kp, frame: M.BodyFrame, limb_mm=None, lo=0.60, hi=1.60) -> dict:
    """(17,3) world-mm skeleton -> {segment: (long, ref)} in UNITY axes."""
    kp = np.asarray(kp, float)
    U = lambda v: to_unity_vec(v, frame) if v is not None else None

    hip_right = _dir(kp, M.L_HIP, M.R_HIP)
    sho_right = _dir(kp, M.L_SHO, M.R_SHO)
    mhip = M._mid(kp[M.L_HIP], kp[M.R_HIP])
    msho = M._mid(kp[M.L_SHO], kp[M.R_SHO])
    trunk = _unit(msho - mhip) if np.all(np.isfinite(mhip)) and np.all(np.isfinite(msho)) else None

    UP, RIGHT, FWD = np.array([0., 1., 0.]), np.array([1., 0., 0.]), np.array([0., 0., 1.])

    out = {}

    def implausible(name):
        """True if this bone's measured length is nowhere near its standing length."""
        if not limb_mm or name not in limb_mm or name not in LIMB_PAIRS:
            return False
        a, b = LIMB_PAIRS[name]
        if not (np.all(np.isfinite(kp[a])) and np.all(np.isfinite(kp[b]))):
            return False
        r = float(np.linalg.norm(kp[b] - kp[a])) / limb_mm[name]
        return r < lo or r > hi

    def put(name, long_w, ref_w, fallback_ref=None, unity_long=None, unity_ref=None):
        if implausible(name):
            return
        lg = unity_long if unity_long is not None else U(long_w)
        rf = unity_ref if unity_ref is not None else U(ref_w)
        b = basis_from(lg, rf, fallback_ref)
        if b is not None:
            out[name] = (b[0], b[1])

    put("pelvis", None, hip_right, fallback_ref=RIGHT, unity_long=UP)
    put("spine1", trunk, sho_right, fallback_ref=RIGHT)
    head_pt = None
    for a, b in ((L_EAR, R_EAR), (L_EYE, R_EYE)):
        if np.all(np.isfinite(kp[a])) and np.all(np.isfinite(kp[b])):
            head_pt = (kp[a] + kp[b]) / 2.0
            break
    if head_pt is None and np.all(np.isfinite(kp[M.NOSE])):
        head_pt = kp[M.NOSE]
    head = (_unit(head_pt - msho)
            if head_pt is not None and np.all(np.isfinite(msho)) else None)
    put("neck", head, sho_right, fallback_ref=RIGHT)

    for side, HIP, KNE, ANK, SHO, ELB, WRI in (
        ("left",  M.L_HIP, M.L_KNE, M.L_ANK, M.L_SHO, L_ELB, L_WRI),
        ("right", M.R_HIP, M.R_KNE, M.R_ANK, M.R_SHO, R_ELB, R_WRI),
    ):
        put(f"{side}_hip",  _dir(kp, HIP, KNE), hip_right, fallback_ref=RIGHT)
        put(f"{side}_knee", _dir(kp, KNE, ANK), hip_right, fallback_ref=RIGHT)
        put(f"{side}_ankle", None, None, unity_long=FWD, unity_ref=UP)

        ua, fa = _dir(kp, SHO, ELB), _dir(kp, ELB, WRI)
        put(f"{side}_shoulder", ua, None, unity_ref=FWD)
        put(f"{side}_elbow",    fa, None, unity_ref=FWD)

    return out


class PoseStreamer:
    """Serialises pose + assessment state into one UDP JSON datagram per frame."""

    def __init__(self, frame: M.BodyFrame = None, host="127.0.0.1", port=5006,
                 origin=None, send_joints=True, target="parallel",
                 subject_mm=None, shoulder_mm=None, mirror=True, limb_mm=None):
        self.frame = frame
        self.addr = (host, int(port))
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.origin = None if origin is None else np.asarray(origin, float)
        self.send_joints = send_joints
        self.mirror = bool(mirror)
        self.limb_mm = limb_mm or {}
        self.seq = 0
        self.target = target
        self.subject_mm = None if subject_mm is None else float(subject_mm)
        self.shoulder_mm = None if shoulder_mm is None else float(shoulder_mm)
        self._trace = []
        self.session = 0

    def stance(self, kp) -> dict:
        """The set-up check, evaluated live on every frame, unlike the engine's one-off stance-width measurement."""
        sw = M.stance_width_ratio(kp, self.frame, shoulder_mm=self.shoulder_mm)
        cls, cue = M.classify_stance_width(sw)
        from metrics import _ok
        return {"ratio": (round(float(sw), 2) if np.isfinite(sw) else None),
                "class": cls, "cue": cue,
                "lo": STANCE_NARROW, "hi": STANCE_WIDE}

    def depth_target(self, scale=1.0) -> dict:
        """The selected depth variation as a millimetre band, drawn from the engine's own thresholds."""
        from rep_engine import DEPTH_OFFSET, PARALLEL_BAND, PARTIAL_MAX_MM
        k = float(scale) if np.isfinite(scale) and scale > 0 else 1.0
        lo, hi = (DEPTH_OFFSET - PARALLEL_BAND) * k, (DEPTH_OFFSET + PARALLEL_BAND) * k
        if self.target == "partial":
            return {"name": "partial", "lo": hi, "hi": PARTIAL_MAX_MM * k}
        if self.target == "deep":
            return {"name": "deep", "lo": None, "hi": lo}
        return {"name": "parallel", "lo": lo, "hi": hi}

    def calibrate(self, frame, origin=None, subject_mm=None, shoulder_mm=None,
                  limb_mm=None):
        """Fill in what only the standing calibration can supply, so one streamer can serve the setup view and then the live session."""
        self.frame = frame
        self.origin = None if origin is None else np.asarray(origin, float)
        self.subject_mm = None if subject_mm is None else float(subject_mm)
        self.shoulder_mm = None if shoulder_mm is None else float(shoulder_mm)
        self.limb_mm = limb_mm or {}

    @staticmethod
    def _cam_counts(conf, cams, thresh=0.5):
        """How many joints each camera can see, so the setup screen can show whether the athlete is framed without any video being streamed."""
        if conf is None or cams is None:
            return None
        c = np.asarray(conf, float)
        if c.ndim != 2 or len(cams) != c.shape[0]:
            return None
        return [{"cam": int(cams[i]), "n": int(np.sum(c[i] >= thresh))}
                for i in range(c.shape[0])]

    def send_setup_pose(self, kp, t, up=None, conf=None, cams=None,
                        countdown=None, note=None, awaiting=False):
        """The pre-calibration view: joints in a provisional frame plus each camera's joint count."""
        pkt = {"seq": self.seq, "session": self.session,
               "t": round(float(t), 4), "phase": "CALIB",
               "countdown": countdown, "note": note,
               "awaiting": int(bool(awaiting)),
               "cams": self._cam_counts(conf, cams)}
        self.seq += 1
        kp = None if kp is None else np.asarray(kp, float)
        present = int(kp is not None and np.isfinite(kp).any())
        pkt["present"] = present
        if present:
            fr = setup_frame(kp, up)
            kpd = mirror_kp(kp, fr, None) if self.mirror else kp
            mank = M._mid(kpd[M.L_ANK], kpd[M.R_ANK])
            mhip = M._mid(kpd[M.L_HIP], kpd[M.R_HIP])
            org = (mank if np.all(np.isfinite(mank))
                   else (mhip if np.all(np.isfinite(mhip)) else None))
            pkt["joints"] = [
                ([round(float(c), 4) for c in to_unity_point(p, fr, org)]
                 if np.all(np.isfinite(p)) else None)
                for p in kpd]
        try:
            self.sock.sendto(json.dumps(pkt).encode("utf-8"), self.addr)
        except OSError:
            pass
        return pkt

    @staticmethod
    def floor_origin(standing_skeletons, frame: M.BodyFrame):
        """A world point on the floor midway between the feet, so the avatar stands on Unity's y=0 and is centred on x=0."""
        mids, heights = [], []
        for kp in standing_skeletons:
            for j in (M.L_ANK, M.R_ANK):
                if np.all(np.isfinite(kp[j])):
                    heights.append(float(np.dot(kp[j], frame.up)))
            m = M._mid(kp[M.L_ANK], kp[M.R_ANK])
            if np.all(np.isfinite(m)):
                mids.append(m)
        if not mids or not heights:
            return None
        mid = np.median(mids, axis=0)
        return mid + (min(heights) - float(np.dot(mid, frame.up))) * frame.up

    @staticmethod
    def subject_shoulder_width(standing_skeletons, frame: M.BodyFrame):
        """Shoulder separation on the lateral axis, in mm, median over the standing calibration frames."""
        d = []
        for kp in standing_skeletons:
            kp = np.asarray(kp, float)
            sL, sR = kp[M.L_SHO], kp[M.R_SHO]
            if np.all(np.isfinite(sL)) and np.all(np.isfinite(sR)):
                d.append(abs(float(np.dot(sL - sR, frame.lateral))))
        return float(np.median(d)) if d else None

    @staticmethod
    def subject_hip_ankle(standing_skeletons, frame: M.BodyFrame = None):
        """The subject's mid-hip to mid-ankle distance in mm (the leg, not the whole body), median over the standing frames."""
        d = []
        for kp in standing_skeletons:
            kp = np.asarray(kp, float)
            mank = M._mid(kp[M.L_ANK], kp[M.R_ANK])
            mhip = M._mid(kp[M.L_HIP], kp[M.R_HIP])
            if np.all(np.isfinite(mank)) and np.all(np.isfinite(mhip)):
                d.append(float(np.linalg.norm(mhip - mank)))
        return float(np.median(d)) if d else None

    @staticmethod
    def subject_ankle_shoulder(standing_skeletons, frame: M.BodyFrame = None):
        """The subject's mid-ankle to mid-shoulder distance in mm, median over the standing calibration frames."""
        d = []
        for kp in standing_skeletons:
            kp = np.asarray(kp, float)
            mank = M._mid(kp[M.L_ANK], kp[M.R_ANK])
            msho = M._mid(kp[M.L_SHO], kp[M.R_SHO])
            if np.all(np.isfinite(mank)) and np.all(np.isfinite(msho)):
                d.append(float(np.linalg.norm(msho - mank)))
        return float(np.median(d)) if d else None

    def packet(self, kp, t, state=None, rep=None, measure_kp=None) -> dict:
        kp = np.asarray(kp, float)
        present = int(kp is not None and np.isfinite(kp).any())
        pkt = {"seq": self.seq, "session": self.session,
               "t": round(float(t), 4), "present": present}
        self.seq += 1
        if not present:
            return pkt

        if self.subject_mm is not None:
            pkt["subject"] = {"hip_ankle_mm": round(self.subject_mm, 1)}
            if self.shoulder_mm is not None:
                pkt["subject"]["shoulder_mm"] = round(self.shoulder_mm, 1)

        kpd = mirror_kp(kp, self.frame, self.origin) if self.mirror else kp
        pkt["mirror"] = int(self.mirror)

        mhip = M._mid(kpd[M.L_HIP], kpd[M.R_HIP])
        if np.all(np.isfinite(mhip)):
            pkt["root"] = [round(float(c), 4)
                           for c in to_unity_point(mhip, self.frame, self.origin)]

        seg = {}
        for name, (lg, rf) in segment_axes(kpd, self.frame, self.limb_mm).items():
            seg[name] = [round(float(c), 4) for c in lg] + [round(float(c), 4) for c in rf]
        pkt["seg"] = seg

        if self.send_joints:
            pkt["joints"] = [
                ([round(float(c), 4) for c in to_unity_point(p, self.frame, self.origin)]
                 if np.all(np.isfinite(p)) else None)
                for p in kpd
            ]
        phase = (state or {}).get("phase")
        if state is not None:
            mk = kp if measure_kp is None else np.asarray(measure_kp, float)
            dm = M.depth_margin(mk, self.frame)
            pkt["state"] = {
                "phase": state.get("phase"),
                "rep": state.get("rep_count"),
                "cue": state.get("live_cue"),
                "cue_key": _cue_key(state.get("live_cue")),
                "cue_short": CUE_SHORT.get(_cue_key(state.get("live_cue"))),
                "knee": state.get("knee_angle"),
                "pelvis_h": state.get("pelvis_h"),
                "depth_mm": (round(float(dm), 1) if np.isfinite(dm) else None),
                "depth_target": self.depth_target(
                    state.get("depth_scale", 1.0)),
                "stance": self.stance(kp),
                "countdown": state.get("countdown"),
                "cams": state.get("cams"),
                "refs_ready": state.get("refs_ready"),
            }
            if np.isfinite(dm):
                self._trace.append(round(float(dm), 1))
            if phase == "SETUP" and not rep:
                self._trace = []
            if len(self._trace) > 400:
                self._trace = self._trace[-400:]
        if rep is not None:
            rep = dict(rep)
            rep["trace"] = list(self._trace)
            rep["depth_band"] = self.depth_target(rep.get("depth_scale", 1.0))
            self._trace = []
            pkt["rep"] = rep
        return pkt

    def send(self, kp, t, state=None, rep=None, measure_kp=None):
        data = json.dumps(self.packet(kp, t, state, rep, measure_kp)).encode("utf-8")
        try:
            self.sock.sendto(data, self.addr)
        except OSError:
            pass
        return len(data)

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


if __name__ == "__main__":
    from synthetic_squat import make_session

    frames = make_session()
    stand = [kp for kp, _ in frames[:25]]
    frame = M.calibrate_body_frame(stand)

    kp = stand[-1]
    axes = segment_axes(kp, frame)
    print(f"segments resolved standing: {len(axes)}/{len(SEGMENT_ORDER)}")
    missing = [s for s in SEGMENT_ORDER if s not in axes]
    print("missing:", missing or "none")

    for name, (e1, e2) in axes.items():
        assert abs(np.dot(e1, e2)) < 1e-9, name
        assert abs(np.linalg.norm(e1) - 1) < 1e-9, name

    o = PoseStreamer.floor_origin(stand, frame)
    lx = to_unity_point(kp[M.L_ANK], frame, o)[0]
    rx = to_unity_point(kp[M.R_ANK], frame, o)[0]
    print(f"left ankle x = {lx:+.3f} m, right ankle x = {rx:+.3f} m  "
          f"(left must be negative = Unity's -X)")
    assert lx < 0 < rx, "CHIRALITY WRONG - avatar would be mirrored"

    y_ank = to_unity_point(kp[M.L_ANK], frame, o)[1]
    y_nose = to_unity_point(kp[M.NOSE], frame, o)[1]
    print(f"ankle y = {y_ank:+.3f} m, nose y = {y_nose:+.3f} m")
    assert abs(y_ank) < 0.02 and y_nose > 1.0

    thigh_y = axes["left_hip"][0][1]
    print(f"standing thigh long-axis y = {thigh_y:+.3f} (must be negative)")
    assert thigh_y < -0.8

    s = PoseStreamer(frame, origin=o)
    n = len(json.dumps(s.packet(kp, 0.0)))
    print(f"packet size = {n} bytes (UDP-safe if < 8000)")
    assert n < 8000
    print("OK")
