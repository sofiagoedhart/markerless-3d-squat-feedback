"""Report the rig's physical geometry from the calibration, for Table 6.1."""
import argparse
import itertools
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def centre(R, t):
    """Camera centre in world coordinates, in mm."""
    return -np.asarray(R, float).T @ np.asarray(t, float).ravel()


def axis(R):
    """Unit vector along the camera's optical axis, pointing where it looks."""
    return np.asarray(R, float).T @ np.array([0.0, 0.0, 1.0])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lens-height", type=float, default=None,
                    help="height of the reference camera's lens above the floor, in mm")
    a = ap.parse_args()

    data = json.load(open("calib/extrinsics.json"))
    cams = data["cameras"]
    ref = str(data.get("reference_camera", sorted(cams)[0]))
    idx = sorted(cams, key=int)

    up = None
    if os.path.exists("calib/vertical.json"):
        v = json.load(open("calib/vertical.json"))
        for k in ("up", "up_world", "vertical"):
            if k in v:
                up = np.asarray(v[k], float).ravel()
                break
    if up is not None:
        up = up / np.linalg.norm(up)

    C = {i: centre(cams[i]["R"], cams[i]["t"]) for i in idx}
    A = {i: axis(cams[i]["R"]) for i in idx}

    print("=" * 70)
    print(f"RIG GEOMETRY from calib/extrinsics.json   (units: {data.get('units','mm')})")
    print(f"reference camera: cam{ref}   vertical: "
          + ("calib/vertical.json" if up is not None else "NOT FOUND - heights omitted"))
    print("=" * 70)

    print("\nCamera positions, relative to the reference camera (mm):")
    for i in idx:
        d = C[i] - C[ref]
        print(f"  cam{i}   x {d[0]:8.0f}   y {d[1]:8.0f}   z {d[2]:8.0f}"
              f"   |offset| {np.linalg.norm(d):7.0f}")

    print("\nCamera separations (baselines, mm):")
    for i, j in itertools.combinations(idx, 2):
        print(f"  cam{i} - cam{j}   {np.linalg.norm(C[i] - C[j]):7.0f}")

    print("\nAngle between optical axes (deg) - the inter-camera angle:")
    for i, j in itertools.combinations(idx, 2):
        c = float(np.clip(np.dot(A[i], A[j]), -1, 1))
        print(f"  cam{i} - cam{j}   {np.degrees(np.arccos(c)):7.1f}")

    if up is not None:
        print("\nHeights along the rig vertical (mm):")
        h = {i: float(np.dot(C[i], up)) for i in idx}
        base = h[ref] - (a.lens_height or 0.0)
        for i in idx:
            rel = h[i] - h[ref]
            if a.lens_height is None:
                print(f"  cam{i}   {rel:+8.0f} relative to cam{ref}")
            else:
                print(f"  cam{i}   {h[i] - base:8.0f} above the floor"
                      f"   ({rel:+.0f} relative to cam{ref})")
        if a.lens_height is None:
            print("  relative only - pass --lens-height <mm> for absolute heights")

        print("\nCamera tilt below horizontal (deg):")
        for i in idx:
            print(f"  cam{i}   {np.degrees(np.arcsin(np.clip(-np.dot(A[i], up), -1, 1))):7.1f}")

    print("\nStill needs a tape measure, because the calibration cannot know it:")
    print("   - height of the reference lens above the floor  (--lens-height)")
    print("   - where the athlete stands, and the usable volume they must stay inside")
    print("   - laptop model and CPU")
    print("Cross-check ONE baseline above against a tape measurement. If they agree")
    print("the calibration's scale is sound, and every other number here follows.")


if __name__ == "__main__":
    main()
