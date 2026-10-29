"""Measure the rig's true vertical from the checkerboard laid flat on the floor."""
import os
import sys
import json
import numpy as np
import cv2

from triangulate_board_accuracy import (
    open_camera, detect, triangulate_board, load_P, CHECKERBOARD,
    load_intrinsics, undistort_corner_dict,
)

_win = {}


def show_cam(win, img, k, width=640):
    """One resizable, movable window per camera (grid: two top, one below)."""
    if win not in _win:
        cv2.namedWindow(win, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)
        try:
            cv2.moveWindow(win, 20 + (k % 2) * (width + 30),
                           60 + (k // 2) * (int(width * 9 / 16) + 80))
        except Exception:
            pass
        _win[win] = False
    cv2.imshow(win, img)
    if not _win[win]:
        h, w = img.shape[:2]
        try:
            cv2.resizeWindow(win, width, int(width * h / w))
        except Exception:
            pass
        _win[win] = True


def load_Rt(indices):
    data = json.load(open("calib/extrinsics.json"))
    Rt = {}
    for i in indices:
        c = data["cameras"][str(i)]
        Rt[i] = (np.array(c["R"], float), np.array(c["t"], float).reshape(3))
    return Rt


def plane_normal(pts):
    """Best-fit plane through the 3D corners as (unit normal, centroid), or None if too few corners are valid."""
    p = pts[~np.any(np.isnan(pts), axis=1)]
    if p.shape[0] < 6:
        return None
    c = p.mean(axis=0)
    _, _, Vt = np.linalg.svd(p - c)
    n = Vt[2]
    return n / np.linalg.norm(n), c


def main(indices):
    Pmats = load_P(indices)
    intr = load_intrinsics(indices)
    Rt = load_Rt(indices)
    centers = {i: -R.T @ t for i, (R, t) in Rt.items()}
    mean_center = np.mean(list(centers.values()), axis=0)

    caps = {i: open_camera(i) for i in indices}
    caps = {i: c for i, c in caps.items() if c is not None}
    if len(caps) < 2:
        print("Need >=2 cameras open.")
        return
    print("Lay the checkerboard FLAT on the floor, visible to >=2 cameras. Hold still.")
    print("Watch the 'up' reading settle (small spread), then press q to save.\n")

    normals = []
    while True:
        corners = {}
        for k, (i, cap) in enumerate(sorted(caps.items())):
            ok, f = cap.read()
            if not ok or f is None:
                continue
            cs = detect(f)
            if cs is not None:
                corners[i] = cs
                cv2.drawChessboardCorners(f, CHECKERBOARD, cs.reshape(-1, 1, 2), True)
            d = cv2.resize(f, (640, 360))
            cv2.putText(d, f"cam{i} {'OK' if cs is not None else '--'}", (12, 34),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0,
                        (0, 255, 0) if cs is not None else (0, 0, 255), 2)
            show_cam(f"vertical calib cam{i} (q saves)", d, k)

        if len(corners) >= 2:
            res = plane_normal(triangulate_board(Pmats, undistort_corner_dict(corners, intr)))
            if res is not None:
                n, cboard = res
                if np.dot(n, mean_center - cboard) < 0:
                    n = -n
                normals.append(n)
                if len(normals) % 5 == 0:
                    up = np.mean(normals[-30:], axis=0); up /= np.linalg.norm(up)
                    spread = np.degrees(np.arccos(np.clip(
                        [np.dot(up, m) for m in normals[-30:]], -1, 1))).std()
                    print(f"  frames {len(normals):3d}   up = {np.round(up, 3)}   "
                          f"spread {spread:.1f} deg")

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    for c in caps.values():
        c.release()
    cv2.destroyAllWindows()

    if len(normals) < 5:
        print("Not enough board-on-floor frames — lay it flat, keep it in view, and retry.")
        return
    up = np.mean(normals[-60:], axis=0); up /= np.linalg.norm(up)
    spread = np.degrees(np.arccos(np.clip([np.dot(up, m) for m in normals[-60:]], -1, 1))).std()
    os.makedirs("calib", exist_ok=True)
    with open("calib/vertical.json", "w") as fh:
        json.dump({"up": up.tolist(), "n_frames": len(normals),
                   "angular_std_deg": float(spread)}, fh, indent=2)
    print(f"\nSaved calib/vertical.json   up = {np.round(up, 3)}   spread {spread:.1f} deg")
    if spread > 3.0:
        print("NOTE: spread > 3 deg — make sure the board was truly flat and still; re-run for a tighter result.")
    print("live_form_feedback.py will now use this as the rig vertical automatically.")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python src/calibrate_vertical.py 0 1 2")
        sys.exit(0)
    main([int(a) for a in sys.argv[1:]])
