"""Solve where each camera sits relative to the reference camera, from synchronised board images."""

import os
import sys
import json
import glob
import itertools
import numpy as np
import cv2

from triangulate_board_accuracy import refine_corners

CHECKERBOARD = (8, 6)
SQUARE_W_MM = 73.5
SQUARE_H_MM = 73.5
SUBPIX = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)


def object_points():
    cols, rows = CHECKERBOARD
    objp = np.zeros((cols * rows, 3), np.float32)
    objp[:, :2] = np.mgrid[0:cols, 0:rows].T.reshape(-1, 2)
    objp[:, 0] *= SQUARE_W_MM
    objp[:, 1] *= SQUARE_H_MM
    return objp


def load_intrinsics(cam):
    path = f"calib/cam{cam}_intrinsics.json"
    if not os.path.exists(path):
        raise FileNotFoundError(f"{path} missing — run calibrate_intrinsics.py {cam} first.")
    with open(path) as f:
        d = json.load(f)
    return (np.array(d["camera_matrix_K"], float),
            np.array(d["dist_coeffs"], float),
            tuple(d["image_size"]))


def detect(path):
    img = cv2.imread(path)
    if img is None:
        return None
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    found, corners = cv2.findChessboardCorners(
        gray, CHECKERBOARD,
        cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE)
    if not found:
        return None
    return refine_corners(gray, corners, CHECKERBOARD)


def set_ids(cam):
    return {os.path.splitext(os.path.basename(f))[0]
            for f in glob.glob(f"calib_images/extrinsic/cam{cam}/set_*.png")}


def pnp_errors(objp, pts_list, K, dist):
    """Per-view reprojection error via solvePnP, used to find blurry or oblique frames."""
    errs = []
    for pts in pts_list:
        ok, rvec, tvec = cv2.solvePnP(objp, pts, K, dist)
        proj, _ = cv2.projectPoints(objp, rvec, tvec, K, dist)
        proj = proj.reshape(-1, 2)
        errs.append(float(np.sqrt(np.mean(np.sum((proj - pts.reshape(-1, 2)) ** 2, axis=1)))))
    return np.array(errs)


def stereo(objpts, ptsref, ptsc, Kr, dr, Kc, dc, size):
    rms, _, _, _, _, R, T, _, _ = cv2.stereoCalibrate(
        objpts, ptsref, ptsc, Kr, dr, Kc, dc, size,
        flags=cv2.CALIB_FIX_INTRINSIC,
        criteria=(cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, 1e-5))
    return rms, R, T


def calibrate_pair(objp, ref, c, Ks, dists, sizes):
    shared = sorted(set_ids(ref) & set_ids(c))
    ptsref, ptsc = [], []
    for sid in shared:
        cr = detect(f"calib_images/extrinsic/cam{ref}/{sid}.png")
        cc = detect(f"calib_images/extrinsic/cam{c}/{sid}.png")
        if cr is not None and cc is not None:
            ptsref.append(cr)
            ptsc.append(cc)
    n = len(ptsref)
    print(f"cam{ref}-cam{c}: {n} shared views with the board in both.")
    if n < 8:
        print(f"  !! too few shared views ({n}); capture more sets where both see the board.")
        return None
    objpts = [objp] * n

    rms, R, T = stereo(objpts, ptsref, ptsc, Ks[ref], dists[ref], Ks[c], dists[c], sizes[ref])
    print(f"  pass 1: stereo RMS {rms:.3f} px over {n} views")

    er = pnp_errors(objp, ptsref, Ks[ref], dists[ref])
    ec = pnp_errors(objp, ptsc, Ks[c], dists[c])
    worst = np.maximum(er, ec)
    keep = worst <= 1.5 * np.median(worst)
    if 8 <= keep.sum() < n:
        o2 = [objp] * int(keep.sum())
        r2 = [ptsref[i] for i in range(n) if keep[i]]
        c2 = [ptsc[i] for i in range(n) if keep[i]]
        rms2, R2, T2 = stereo(o2, r2, c2, Ks[ref], dists[ref], Ks[c], dists[c], sizes[ref])
        if rms2 < rms:
            print(f"  pass 2: stereo RMS {rms2:.3f} px (dropped {n - keep.sum()} outlier view(s))")
            rms, R, T = rms2, R2, T2
    baseline = float(np.linalg.norm(T))
    print(f"  RESULT stereo RMS {rms:.3f} px   baseline {baseline:.0f} mm "
          f"({'good' if rms < 1.0 else 'usable' if rms < 2.0 else 'high — see notes'})")
    return R, T


def main(indices):
    ref = indices[0]
    objp = object_points()
    Ks, dists, sizes = {}, {}, {}
    for c in indices:
        Ks[c], dists[c], sizes[c] = load_intrinsics(c)

    result = {"reference_camera": ref, "units": "mm", "cameras": {}}
    R0, t0 = np.eye(3), np.zeros((3, 1))
    result["cameras"][str(ref)] = {
        "K": Ks[ref].tolist(), "R": R0.tolist(), "t": t0.ravel().tolist(),
        "P": (Ks[ref] @ np.hstack([R0, t0])).tolist()}

    for c in indices[1:]:
        out = calibrate_pair(objp, ref, c, Ks, dists, sizes)
        if out is None:
            continue
        R, T = out
        result["cameras"][str(c)] = {
            "K": Ks[c].tolist(), "R": R.tolist(), "t": T.ravel().tolist(),
            "P": (Ks[c] @ np.hstack([R, T])).tolist()}

    os.makedirs("calib", exist_ok=True)
    with open("calib/extrinsics.json", "w") as f:
        json.dump(result, f, indent=2)

    print("\nGeometry (reference cam{} at origin):".format(ref))
    centres = {}
    for cid, cc in result["cameras"].items():
        R = np.array(cc["R"]); t = np.array(cc["t"]).reshape(3, 1)
        C = (-R.T @ t).ravel()
        centres[cid] = C
        print(f"  cam{cid} centre (mm): [{C[0]:8.0f} {C[1]:8.0f} {C[2]:8.0f}]")
    for a, b in itertools.combinations(centres, 2):
        print(f"  baseline cam{a}-cam{b}: {np.linalg.norm(centres[a]-centres[b]):.0f} mm")
    print(f"\nSaved calib/extrinsics.json for cameras {list(result['cameras'])} (reference = cam{ref}).")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python src/calibrate_extrinsics.py 1 0 2   (first = reference; use centre cam)")
        sys.exit(0)
    main([int(a) for a in sys.argv[1:]])
