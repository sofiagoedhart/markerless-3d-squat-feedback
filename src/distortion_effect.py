"""Measure what lens-distortion correction changes, on a recorded squat set."""
import argparse
import json
import os
import sys

import numpy as np
import cv2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import metrics as M
from multiview_triangulate import Camera, triangulate_skeleton
from session_io import load_session_arrays, body_frame_from_meta


def load_rig():
    """Cameras from calib/extrinsics.json, each carrying its distortion coefficients."""
    data = json.load(open("calib/extrinsics.json"))
    rig, order = [], []
    for i in sorted(data["cameras"], key=int):
        c = data["cameras"][i]
        p = f"calib/cam{i}_intrinsics.json"
        dist = None
        if os.path.exists(p):
            dist = np.asarray(json.load(open(p))["dist_coeffs"], float).ravel()
        rig.append(Camera(np.array(c["K"]), np.array(c["R"]), np.array(c["t"]),
                          name=f"cam{i}", dist=dist))
        order.append(int(i))
    return rig, order


def stats(v):
    v = np.asarray([x for x in v if np.isfinite(x)], float)
    if not len(v):
        return float("nan"), float("nan"), float("nan")
    return float(v.mean()), float(np.median(v)), float(np.percentile(v, 95))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("session")
    a = ap.parse_args()

    d = load_session_arrays(a.session)
    pts, conf = d["pts2d"], d["conf"]
    rig, _ = load_rig()
    frame = body_frame_from_meta(d["meta"])

    d2d, d3d = [], []
    rows = {k: [] for k in ("depth", "gap", "tilt", "knee")}
    used = 0
    for f in range(len(pts)):
        p, c = np.asarray(pts[f], float), np.asarray(conf[f], float)
        if not np.any(np.isfinite(p)):
            continue
        on, _ = triangulate_skeleton(rig, p, c, undistort=True)
        off, _ = triangulate_skeleton(rig, p, c, undistort=False)
        if on is None or off is None:
            continue
        used += 1

        for ci, cam in enumerate(rig):
            if cam.dist is None:
                continue
            q = p[ci]
            ok = np.all(np.isfinite(q), axis=1)
            if not np.any(ok):
                continue
            fixed = cv2.undistortPoints(q[ok].reshape(-1, 1, 2), cam.K,
                                        cam.dist, P=cam.K).reshape(-1, 2)
            d2d.extend(np.linalg.norm(fixed - q[ok], axis=1))

        m = np.linalg.norm(on - off, axis=1)
        d3d.extend(m[np.isfinite(m)])

        for key, fn in (("depth", lambda k: M.depth_margin(k, frame)),
                        ("gap",   lambda k: M.knee_separation(k, frame)),
                        ("tilt",  lambda k: M.shoulder_tilt(k, frame)),
                        ("knee",  lambda k: M.knee_signal(k))):
            x, y = fn(on), fn(off)
            if np.isfinite(x) and np.isfinite(y):
                rows[key].append(abs(x - y))

    name = os.path.basename(a.session).replace(".npz", "")
    out = [f"Lens-distortion correction, measured on {name}",
           f"frames compared: {used} of {len(pts)} recorded", "",
           f"  {'quantity':<32}{'mean':>9}{'median':>9}{'95th pct':>11}"]
    for label, v in (("2D keypoint position (px)", d2d),
                     ("3D joint position (mm)", d3d),
                     ("Depth margin (mm)", rows["depth"]),
                     ("Knee separation (mm)", rows["gap"]),
                     ("Shoulder tilt (deg)", rows["tilt"]),
                     ("Knee angle (deg)", rows["knee"])):
        mu, md, p95 = stats(v)
        out.append(f"  {label:<32}{mu:>9.2f}{md:>9.2f}{p95:>11.2f}")

    text = "\n".join(out)
    print(text)
    os.makedirs("results", exist_ok=True)
    with open("results/distortion_effect.txt", "w") as fh:
        fh.write(text + "\n")
    print("\nwrote results/distortion_effect.txt")


if __name__ == "__main__":
    main()
