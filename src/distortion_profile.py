"""How far lens-distortion correction moves a point, as a function of image radius."""
import argparse
import json
import os
import sys

import numpy as np
import cv2


def load(i):
    p = f"calib/cam{i}_intrinsics.json"
    if not os.path.exists(p):
        return None, None
    d = json.load(open(p))
    K = np.asarray(d["camera_matrix_K"], float)
    dist = np.asarray(d["dist_coeffs"], float).ravel()
    return K, dist


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("indices", nargs="*", type=int, default=[0, 1, 2])
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    a = ap.parse_args()

    print(f"Correction displacement vs image radius, {a.width}x{a.height}.")
    print("Radius is measured from the principal point; 1.0 is the image corner.\n")
    fracs = [0.25, 0.50, 0.75, 1.00]
    print(f"  {'camera':<9}" + "".join(f"{f'r={f:.2f}':>12}" for f in fracs)
          + f"{'k1':>10}{'k2':>10}")
    rows = {}
    for i in a.indices:
        K, dist = load(i)
        if K is None:
            print(f"  cam{i}: no intrinsics file")
            continue
        cx, cy = K[0, 2], K[1, 2]
        rmax = float(np.hypot(max(cx, a.width - cx), max(cy, a.height - cy)))
        out = []
        for f in fracs:
            r = f * rmax
            th = np.linspace(0, 2 * np.pi, 180, endpoint=False)
            pts = np.stack([cx + r * np.cos(th), cy + r * np.sin(th)], 1)
            fixed = cv2.undistortPoints(pts.reshape(-1, 1, 2).astype(np.float64),
                                        K, dist, P=K).reshape(-1, 2)
            out.append(float(np.mean(np.linalg.norm(fixed - pts, axis=1))))
        rows[i] = out
        print(f"  cam{i:<8}" + "".join(f"{v:>11.2f}px" for v in out)
              + f"{dist[0]:>10.3f}{dist[1]:>10.3f}")

    if rows:
        arr = np.array(list(rows.values()))
        print("\n  mean over cameras:")
        for f, v in zip(fracs, arr.mean(0)):
            print(f"    r = {f:.2f} of the corner radius -> {v:6.2f} px")


if __name__ == "__main__":
    main()
