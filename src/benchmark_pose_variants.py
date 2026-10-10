"""Compare YOLO pose variants on this rig, in the units the assessment engine cares about."""

import argparse
import csv
import json
import os
import sys
import time

import numpy as np

try:
    import cv2
except ImportError:
    sys.exit("opencv is required:  pip install opencv-python")

try:
    from ultralytics import YOLO
except ImportError:
    sys.exit("ultralytics is required:  pip install ultralytics")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from multiview_triangulate import Camera, triangulate_skeleton, N_JOINTS
from dlt_triangulation import project

CAP_WIDTH, CAP_HEIGHT = 1280, 720
CONF_THRESH = 0.5
MIN_VIEWS = 2
DEFAULT_MODELS = ["yolo11n-pose.pt", "yolo11s-pose.pt", "yolo11m-pose.pt"]

L_SHO, R_SHO = 5, 6
L_HIP, R_HIP = 11, 12
L_KNE, R_KNE = 13, 14
L_ANK, R_ANK = 15, 16

SCORING_JOINTS = [L_SHO, R_SHO, L_HIP, R_HIP, L_KNE, R_KNE, L_ANK, R_ANK]


def pick_device():
    try:
        import torch
        if torch.backends.mps.is_available():
            return "mps"
        if torch.cuda.is_available():
            return "cuda"
    except Exception:
        pass
    return "cpu"


def load_rig(indices, calib_path="calib/extrinsics.json"):
    """Build a Camera per index from the extrinsics file (same as live_triangulate)."""
    if not os.path.exists(calib_path):
        sys.exit(f"Calibration not found: {calib_path}\n"
                 f"Run the extrinsic calibration first.")
    data = json.load(open(calib_path))
    cams = data["cameras"]
    rig = []
    for i in indices:
        if str(i) not in cams:
            sys.exit(f"cam{i} not in {calib_path} (has {list(cams)}).")
        c = cams[str(i)]
        rig.append(Camera(np.array(c["K"]), np.array(c["R"]),
                          np.array(c["t"]), name=f"cam{i}"))
    print(f"Rig loaded from {calib_path} (units: {data.get('units', 'mm')})")
    return rig


def open_live(index):
    cap = cv2.VideoCapture(index, cv2.CAP_AVFOUNDATION)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAP_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAP_HEIGHT)
    for _ in range(45):
        ok, f = cap.read()
        if ok and f is not None and f.mean() > 5:
            return cap
        time.sleep(0.03)
    sys.exit(f"Camera {index} would not start.")
    return None


def best_person(res):
    """(17,2) xy and (17,) conf for the highest-confidence detection."""
    kp = res.keypoints
    if kp is None or kp.xy is None or kp.xy.shape[0] == 0:
        return None, None
    if res.boxes is not None and res.boxes.conf is not None and len(res.boxes.conf) > 0:
        idx = int(res.boxes.conf.argmax())
    else:
        idx = 0
    xy = kp.xy[idx].cpu().numpy()
    conf = kp.conf[idx].cpu().numpy() if kp.conf is not None else np.ones(N_JOINTS)
    return xy, conf


def joint_angle(a, b, c):
    """Angle at b, in degrees, formed by a-b-c."""
    if a is None or b is None or c is None:
        return np.nan
    if np.any(np.isnan(a)) or np.any(np.isnan(b)) or np.any(np.isnan(c)):
        return np.nan
    v1, v2 = a - b, c - b
    n1, n2 = np.linalg.norm(v1), np.linalg.norm(v2)
    if n1 < 1e-6 or n2 < 1e-6:
        return np.nan
    cosang = np.clip(np.dot(v1, v2) / (n1 * n2), -1.0, 1.0)
    return float(np.degrees(np.arccos(cosang)))


def run_variant(model_name, frames_per_cam, rig, device, imgsz=640):
    """Run one model over the pre-loaded frames and collect all metrics."""
    print(f"\n--- {model_name} @ imgsz {imgsz} ---")
    model = YOLO(model_name)
    n_cams = len(rig)
    n_frames = min(len(f) for f in frames_per_cam)

    warm = [frames_per_cam[c][0] for c in range(n_cams)]
    model(warm, device=device, verbose=False, imgsz=imgsz)

    infer_times, pipe_times = [], []
    kp2d_hist = np.full((n_frames, n_cams, N_JOINTS, 2), np.nan)
    reproj_errs = []
    knee_L, knee_R = [], []
    dropouts = 0
    scored_frames = 0

    for k in range(n_frames):
        batch = [frames_per_cam[c][k] for c in range(n_cams)]

        t0 = time.perf_counter()
        results = model(batch, device=device, verbose=False, imgsz=imgsz)
        t1 = time.perf_counter()

        pts = np.full((n_cams, N_JOINTS, 2), np.nan)
        cfs = np.zeros((n_cams, N_JOINTS))
        for c, res in enumerate(results):
            xy, conf = best_person(res)
            if xy is not None:
                pts[c] = xy
                cfs[c] = conf
                trusted = xy.astype(float).copy()
                trusted[conf < CONF_THRESH] = np.nan
                kp2d_hist[k, c] = trusted

        joints3d, n_views = triangulate_skeleton(
            rig, pts, cfs,
            conf_thresh=CONF_THRESH, min_views=MIN_VIEWS,
        )
        t2 = time.perf_counter()

        infer_times.append(t1 - t0)
        pipe_times.append(t2 - t0)

        missing = any(np.any(np.isnan(joints3d[j])) for j in SCORING_JOINTS)
        if missing:
            dropouts += 1
        else:
            scored_frames += 1

        for j in SCORING_JOINTS:
            if np.any(np.isnan(joints3d[j])):
                continue
            for c in range(n_cams):
                obs = pts[c, j]
                if np.any(np.isnan(obs)) or cfs[c, j] < CONF_THRESH:
                    continue
                uv = project(rig[c].P, joints3d[j])
                if np.all(np.isfinite(uv)):
                    reproj_errs.append(float(np.linalg.norm(obs - uv)))

        knee_L.append(joint_angle(joints3d[L_HIP], joints3d[L_KNE], joints3d[L_ANK]))
        knee_R.append(joint_angle(joints3d[R_HIP], joints3d[R_KNE], joints3d[R_ANK]))

    jits = []
    for c in range(n_cams):
        for j in SCORING_JOINTS:
            track = kp2d_hist[:, c, j, :]
            good = track[~np.isnan(track).any(axis=1)]
            if len(good) < 5:
                continue
            dev = good - good.mean(axis=0)
            jits.append(float(np.sqrt((dev ** 2).sum(axis=1).mean())))

    kneeL = np.array(knee_L, dtype=float)
    kneeR = np.array(knee_R, dtype=float)
    knee_all = np.concatenate([kneeL[~np.isnan(kneeL)], kneeR[~np.isnan(kneeR)]])

    return {
        "model": f"{model_name.replace('.pt', '')}@{imgsz}",
        "imgsz": imgsz,
        "frames": n_frames,
        "fps_infer": 1.0 / np.mean(infer_times) if infer_times else np.nan,
        "fps_pipeline": 1.0 / np.mean(pipe_times) if pipe_times else np.nan,
        "jitter_px": float(np.mean(jits)) if jits else np.nan,
        "reproj_px": float(np.mean(reproj_errs)) if reproj_errs else np.nan,
        "knee_deg_std": float(np.std(knee_all)) if len(knee_all) > 5 else np.nan,
        "dropout_pct": 100.0 * dropouts / max(1, n_frames),
    }


def load_clips(paths, max_frames, skip=0):
    """Read each clip fully into memory so every variant sees identical frames."""
    per_cam = []
    for p in paths:
        if not os.path.exists(p):
            sys.exit(f"Clip not found: {p}")
        cap = cv2.VideoCapture(p)
        for _ in range(skip):
            if not cap.grab():
                break
        frames = []
        while len(frames) < max_frames:
            ok, f = cap.read()
            if not ok:
                break
            frames.append(f)
        cap.release()
        if not frames:
            sys.exit(f"No frames read from {p}")
        print(f"  {p}: {len(frames)} frames")
        per_cam.append(frames)
    n = min(len(f) for f in per_cam)
    if len(set(len(f) for f in per_cam)) > 1:
        print(f"  ! clips differ in length; truncating all to {n} frames")
    return [f[:n] for f in per_cam]


def capture_live(indices, n_frames):
    caps = [open_live(i) for i in indices]
    per_cam = [[] for _ in indices]
    print(f"Capturing {n_frames} synchronised frames...")
    for k in range(n_frames):
        for c, cap in enumerate(caps):
            ok, f = cap.read()
            if ok and f is not None:
                per_cam[c].append(f)
    for cap in caps:
        cap.release()
    n = min(len(f) for f in per_cam)
    return [f[:n] for f in per_cam]


def write_latex(rows, path, static):
    """Emit a table body matching tab:pose-rig in Chapter 3."""
    def fmt(v, nd=2):
        return "---" if (v is None or (isinstance(v, float) and np.isnan(v))) else f"{v:.{nd}f}"

    lines = [
        "% Auto-generated by src/benchmark_pose_variants.py",
        "% Paste the rows below into tab:pose-rig in 03_highlevel_design.tex",
        f"% Clip type: {'STATIC HOLD' if static else 'MOVING'} "
        f"({'jitter/knee columns valid' if static else 'jitter/knee columns NOT meaningful'})",
        "",
    ]
    for r in rows:
        name = r["model"].replace("yolo11", "YOLO11").replace("-pose", "-pose")
        lines.append(
            f"    {name} & {fmt(r['fps_pipeline'],1)} & {fmt(r['jitter_px'])} & "
            f"{fmt(r['reproj_px'])} & {fmt(r['knee_deg_std'])} \\\\"
        )
    with open(path, "w") as fh:
        fh.write("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--clips", nargs="+", metavar="MP4",
                     help="one recorded clip per camera, frame-aligned (preferred)")
    src.add_argument("--live", action="store_true",
                     help="capture from the rig now (less reproducible)")
    ap.add_argument("--cams", nargs="+", type=int, required=True,
                    help="camera indices, in the SAME order as --clips, matching calibration")
    ap.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    ap.add_argument("--frames", type=int, default=300,
                    help="max frames to evaluate (default 300)")
    ap.add_argument("--skip", type=int, default=0,
                    help="discard this many frames at the start of each clip -- "
                         "use it to land on a genuinely still window")
    ap.add_argument("--imgsz", nargs="+", type=int, default=[640],
                    help="inference sizes to compare, e.g. --imgsz 640 1280")
    ap.add_argument("--static", action="store_true",
                    help="mark this clip as a static hold, so jitter/knee columns are valid")
    ap.add_argument("--calib", default="calib/extrinsics.json")
    ap.add_argument("--outdir", default="results")
    args = ap.parse_args()

    if args.clips and len(args.clips) != len(args.cams):
        sys.exit("--clips and --cams must have the same number of entries, in the same order.")

    os.makedirs(args.outdir, exist_ok=True)
    device = pick_device()
    print(f"Device: {device}")
    rig = load_rig(args.cams, args.calib)

    print("Loading frames...")
    if args.clips:
        frames = load_clips(args.clips, args.frames, args.skip)
    else:
        frames = capture_live(args.cams, args.frames)
    print(f"{len(frames[0])} synchronised frames x {len(rig)} cameras")

    if not args.static:
        print("\nNOTE: --static not set. jitter_px and knee_deg_std assume the subject\n"
              "      is holding still; on a moving clip they measure motion, not noise.")

    rows = [run_variant(m, frames, rig, device, sz)
            for m in args.models for sz in args.imgsz]

    hdr = f"\n{'model':<22}{'fps_inf':>9}{'fps_pipe':>10}{'jitter_px':>11}{'reproj_px':>11}{'knee_std':>10}{'dropout%':>10}"
    print(hdr)
    print("-" * len(hdr.strip()))
    for r in rows:
        print(f"{r['model']:<22}{r['fps_infer']:>9.1f}{r['fps_pipeline']:>10.1f}"
              f"{r['jitter_px']:>11.2f}{r['reproj_px']:>11.2f}"
              f"{r['knee_deg_std']:>10.2f}{r['dropout_pct']:>10.1f}")

    csv_path = os.path.join(args.outdir, "pose_benchmark.csv")
    with open(csv_path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    tex_path = os.path.join(args.outdir, "pose_benchmark_table.tex")
    write_latex(rows, tex_path, args.static)

    print(f"\nWrote {csv_path}")
    print(f"Wrote {tex_path}  <- paste into tab:pose-rig")
    print("\nReminder: no Kalman filtering was applied. Compare variants raw, then\n"
          "filter the one you choose.")


if __name__ == "__main__":
    main()
