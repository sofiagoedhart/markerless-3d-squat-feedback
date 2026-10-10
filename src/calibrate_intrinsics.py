"""Solve one camera's intrinsic matrix and lens distortion from its captured board images."""

import os
import sys
import json
import glob
import numpy as np
import cv2

from triangulate_board_accuracy import refine_corners

CHECKERBOARD = (8, 6)
SQUARE_W_MM = 73.5
SQUARE_H_MM = 73.5

FIX_ASPECT = os.environ.get("FIX_ASPECT", "1") == "1"
CALIB_FLAGS = cv2.CALIB_FIX_K3 | (cv2.CALIB_FIX_ASPECT_RATIO if FIX_ASPECT else 0)
SUBPIX = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)


def object_points():
    """3D board points, using the measured square spacing."""
    cols, rows = CHECKERBOARD
    objp = np.zeros((cols * rows, 3), np.float32)
    objp[:, :2] = np.mgrid[0:cols, 0:rows].T.reshape(-1, 2)
    objp[:, 0] *= SQUARE_W_MM
    objp[:, 1] *= SQUARE_H_MM
    return objp


def per_image_errors(objpts, imgpts, rvecs, tvecs, K, dist):
    errs = []
    for i in range(len(objpts)):
        proj, _ = cv2.projectPoints(objpts[i], rvecs[i], tvecs[i], K, dist)
        proj = proj.reshape(-1, 2)
        obs = imgpts[i].reshape(-1, 2)
        errs.append(float(np.sqrt(np.mean(np.sum((proj - obs) ** 2, axis=1)))))
    return np.array(errs)


def calibrate(objpts, imgpts, image_size):
    rms, K, dist, rvecs, tvecs = cv2.calibrateCamera(
        objpts, imgpts, image_size, None, None, flags=CALIB_FLAGS)
    return rms, K, dist, rvecs, tvecs


def main(cam_index):
    folder = f"calib_images/intrinsic/cam{cam_index}"
    files = sorted(glob.glob(f"{folder}/*.png"))
    if not files:
        print(f"No images in {folder}. Capture first.")
        return
    print(f"cam{cam_index}: {len(files)} images found.")
    print(f"  board model: {CHECKERBOARD[0]}x{CHECKERBOARD[1]} inner corners, "
          f"{SQUARE_W_MM} x {SQUARE_H_MM} mm squares, "
          f"fix_aspect={'ON (fx=fy)' if FIX_ASPECT else 'OFF'}")

    objp = object_points()
    objpts, imgpts, used = [], [], []
    image_size = None
    for f in files:
        img = cv2.imread(f)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        image_size = gray.shape[::-1]
        found, corners = cv2.findChessboardCorners(
            gray, CHECKERBOARD,
            cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE)
        if not found:
            print(f"  board NOT found in {os.path.basename(f)} (skipped)")
            continue
        corners = refine_corners(gray, corners, CHECKERBOARD)
        objpts.append(objp)
        imgpts.append(corners)
        used.append(f)
    if len(objpts) < 5:
        print(f"Only {len(objpts)} usable images — capture more (need >=5, ~15+ ideal).")
        return

    rms, K, dist, rvecs, tvecs = calibrate(objpts, imgpts, image_size)
    errs = per_image_errors(objpts, imgpts, rvecs, tvecs, K, dist)
    print(f"  pass 1: RMS {rms:.3f} px over {len(objpts)} images "
          f"(worst image {errs.max():.2f})")

    med = np.median(errs)
    keep = errs <= 1.5 * med
    if keep.sum() >= 5 and keep.sum() < len(objpts):
        o2 = [objpts[i] for i in range(len(objpts)) if keep[i]]
        i2 = [imgpts[i] for i in range(len(objpts)) if keep[i]]
        rms2, K2, dist2, rv2, tv2 = calibrate(o2, i2, image_size)
        if rms2 < rms:
            dropped = len(objpts) - keep.sum()
            print(f"  pass 2: RMS {rms2:.3f} px (dropped {dropped} outlier image(s))")
            rms, K, dist, objpts, imgpts = rms2, K2, dist2, o2, i2

    fx, fy, cx, cy = K[0, 0], K[1, 1], K[0, 2], K[1, 2]
    w, h = image_size
    print(f"  RESULT  RMS={rms:.3f}px   fx={fx:.1f} fy={fy:.1f} (fx/fy={fx/fy:.4f})"
          f"   cx={cx:.1f} cy={cy:.1f}")
    print(f"  principal point offset from image centre: "
          f"dx={cx - w/2:+.1f} px, dy={cy - h/2:+.1f} px  "
          f"(want within ~5% of size, i.e. |dx|<{0.05*w:.0f}, |dy|<{0.05*h:.0f})")
    print("  -> " + ("GOOD (<1.0 px)" if rms < 1.0 else "acceptable, but aim <1.0 (recapture with sharper/edge-covering shots)"))

    os.makedirs("calib", exist_ok=True)
    out = {
        "camera_index": cam_index,
        "camera_matrix_K": K.tolist(),
        "dist_coeffs": dist.ravel().tolist(),
        "rms_reprojection_error_px": float(rms),
        "image_size": list(image_size),
        "square_w_mm": SQUARE_W_MM,
        "square_h_mm": SQUARE_H_MM,
        "num_images_used": len(objpts),
        "fix_aspect_ratio": FIX_ASPECT,
    }
    with open(f"calib/cam{cam_index}_intrinsics.json", "w") as fh:
        json.dump(out, fh, indent=2)
    np.savez(f"calib/cam{cam_index}_intrinsics.npz", K=K, dist=dist,
             image_size=image_size, rms=rms)

    img = cv2.imread(used[0])
    und = cv2.undistort(img, K, dist)
    cv2.imwrite(f"calib/cam{cam_index}_undistort_preview.png",
                cv2.hconcat([cv2.resize(img, (640, 360)), cv2.resize(und, (640, 360))]))
    print(f"  saved calib/cam{cam_index}_intrinsics.json (+ .npz, undistort preview)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python src/calibrate_intrinsics.py <cam_index>   e.g. 0")
        sys.exit(0)
    main(int(sys.argv[1]))
