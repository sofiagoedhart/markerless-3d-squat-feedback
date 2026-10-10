"""Measure 3D reconstruction accuracy by triangulating the checkerboard against its known pitch."""

import os
import sys
import json
import numpy as np
import cv2
try:
    import viz
except Exception:
    pass

from dlt_triangulation import triangulate_point_dlt

CHECKERBOARD = (8, 6)
SQUARE_W_MM = 73.5
SQUARE_H_MM = 73.5
CAP_WIDTH, CAP_HEIGHT = 1280, 720
SUBPIX = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)

STILL_PX = 0.8


def open_camera(index):
    import time
    cap = cv2.VideoCapture(index, cv2.CAP_AVFOUNDATION)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAP_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAP_HEIGHT)
    try:
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    except Exception:
        pass
    for _ in range(45):
        ok, f = cap.read()
        if ok and f is not None and f.mean() > 5:
            return cap
        time.sleep(0.03)
    return None


def grab_synced(caps):
    """Capture one frame per camera with MINIMAL inter-camera desync."""
    for cap in caps.values():
        cap.grab()
    frames = {}
    for i, cap in caps.items():
        ok, f = cap.retrieve()
        if ok and f is not None:
            frames[i] = f
    return frames


def max_corner_shift(prev, cur):
    """Largest per-corner movement (px) between two corner dicts, over the cameras present in both."""
    shared = [i for i in cur if i in prev]
    if not shared:
        return float("inf")
    return max(float(np.abs(cur[i] - prev[i]).max()) for i in shared)


def load_P(indices):
    data = json.load(open("calib/extrinsics.json"))
    return {i: np.array(data["cameras"][str(i)]["P"]) for i in indices}


def load_intrinsics(indices):
    """Per-camera (K, dist_coeffs) from calib/cam<i>_intrinsics.json."""
    out = {}
    for i in indices:
        path = f"calib/cam{i}_intrinsics.json"
        if not os.path.exists(path):
            print(f"  WARNING: {path} missing -- cam{i} points will NOT be undistorted.")
            continue
        d = json.load(open(path))
        out[i] = (np.array(d["camera_matrix_K"], dtype=np.float64),
                  np.array(d["dist_coeffs"], dtype=np.float64))
    return out


def undistort_points(pts, K, dist):
    """Map raw detected pixels to where an IDEAL PINHOLE camera with the same K would have seen them, so they are consistent with P = K[R|t]."""
    p = np.asarray(pts, dtype=np.float64).reshape(-1, 1, 2)
    return cv2.undistortPoints(p, K, dist, P=K).reshape(-1, 2)


def undistort_corner_dict(corners, intr):
    """Apply undistort_points to every camera in a {cam: (N,2)} dict."""
    return {i: (undistort_points(cs, *intr[i]) if i in intr else cs)
            for i, cs in corners.items()}


def corner_spacing(corners, checkerboard=CHECKERBOARD):
    """Median distance between neighbouring inner corners, in pixels."""
    cols, rows = checkerboard
    p = np.asarray(corners, dtype=float).reshape(rows, cols, 2)
    dx = np.linalg.norm(np.diff(p, axis=1), axis=2).ravel()
    dy = np.linalg.norm(np.diff(p, axis=0), axis=2).ravel()
    return float(np.median(np.concatenate([dx, dy])))


def refine_corners(gray, corners, checkerboard=CHECKERBOARD):
    """CornerSubPix with a search window sized to the board's ON-SCREEN scale."""
    half = int(max(2, min(11, corner_spacing(corners, checkerboard) / 3.0)))
    return cv2.cornerSubPix(gray, corners, (half, half), (-1, -1), SUBPIX)


def detect(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    found, corners = cv2.findChessboardCorners(
        gray, CHECKERBOARD, cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE)
    if not found:
        return None
    return refine_corners(gray, corners).reshape(-1, 2)


def rig_centre(indices):
    """Mean camera centre in world mm, from calib/extrinsics.json."""
    d = json.load(open("calib/extrinsics.json"))["cameras"]
    cs = []
    for i in indices:
        if str(i) not in d:
            continue
        R = np.array(d[str(i)]["R"], float)
        t = np.array(d[str(i)]["t"], float).reshape(3, 1)
        cs.append((-R.T @ t).ravel())
    return np.mean(cs, axis=0)


def oriented_spacings(pts3d, centre):
    """Every adjacent-corner spacing, tagged with how much it points ALONG the viewing direction (depth) versus ACROSS it (lateral)."""
    cols, rows = CHECKERBOARD
    out = []

    def idx(r, c):
        return r * cols + c

    pairs = ([(idx(r, c), idx(r, c + 1), SQUARE_W_MM)
              for r in range(rows) for c in range(cols - 1)] +
             [(idx(r, c), idx(r + 1, c), SQUARE_H_MM)
              for r in range(rows - 1) for c in range(cols)])
    for ia, ib, known in pairs:
        a, b = pts3d[ia], pts3d[ib]
        if np.any(np.isnan(a)) or np.any(np.isnan(b)):
            continue
        v = b - a
        L = float(np.linalg.norm(v))
        if L < 1e-6:
            continue
        view = (a + b) / 2.0 - centre
        nv = np.linalg.norm(view)
        if nv < 1e-6:
            continue
        cosang = abs(float(np.dot(v / L, view / nv)))
        out.append((L - known, float(np.degrees(np.arccos(min(1.0, cosang))))))
    return out


def triangulate_board(Pmats, corner_lists):
    """Corner_lists: {cam_idx: (48,2)}."""
    cols, rows = CHECKERBOARD
    n = cols * rows
    pts3d = np.full((n, 3), np.nan)
    cams = list(corner_lists)
    for j in range(n):
        Ps = [Pmats[c] for c in cams]
        p2 = [corner_lists[c][j] for c in cams]
        if len(Ps) >= 2:
            pts3d[j] = triangulate_point_dlt(Ps, p2)
    return pts3d


def spacing_errors(pts3d):
    """Adjacent-corner spacing errors vs known 60/57.5 mm."""
    cols, rows = CHECKERBOARD
    h_err, v_err = [], []
    def idx(r, c):
        return r * cols + c
    for r in range(rows):
        for c in range(cols - 1):
            a, b = pts3d[idx(r, c)], pts3d[idx(r, c + 1)]
            if not (np.any(np.isnan(a)) or np.any(np.isnan(b))):
                h_err.append(float(np.linalg.norm(a - b) - SQUARE_W_MM))
    for r in range(rows - 1):
        for c in range(cols):
            a, b = pts3d[idx(r, c)], pts3d[idx(r + 1, c)]
            if not (np.any(np.isnan(a)) or np.any(np.isnan(b))):
                v_err.append(float(np.linalg.norm(a - b) - SQUARE_H_MM))
    return h_err, v_err


def span_errors(pts3d):
    """Full-width and full-height spans — sensitive to overall scale."""
    cols, rows = CHECKERBOARD
    errs = []
    known_w = (cols - 1) * SQUARE_W_MM
    known_h = (rows - 1) * SQUARE_H_MM
    for r in range(rows):
        a, b = pts3d[r * cols], pts3d[r * cols + (cols - 1)]
        if not (np.any(np.isnan(a)) or np.any(np.isnan(b))):
            errs.append(("width", float(np.linalg.norm(a - b) - known_w)))
    for c in range(cols):
        a, b = pts3d[c], pts3d[(rows - 1) * cols + c]
        if not (np.any(np.isnan(a)) or np.any(np.isnan(b))):
            errs.append(("height", float(np.linalg.norm(a - b) - known_h)))
    return errs


def orientation_report(oriented):
    """Split the spacing errors by segment orientation -- the fx discriminator."""
    if not oriented:
        return ["orientation split: no samples"]
    e = np.array([o[0] for o in oriented])
    a = np.array([o[1] for o in oriented])
    lines = ["",
             "ORIENTATION SPLIT  (0 deg = segment points ALONG depth, 90 = across view)",
             "  If fx is correct these agree. If fx is wrong the along-depth rows",
             "  carry a much larger bias -- depth error goes as s^2, lateral as s.",
             f"  {'bucket':>16} {'n':>6} {'bias mm':>9} {'scatter':>9} {'|err| med':>10}"]
    for lo, hi, tag in ((0, 30, "along depth"), (30, 60, "diagonal"), (60, 90, "across view")):
        m = (a >= lo) & (a < hi if hi < 90 else a <= 90)
        if m.sum() < 10:
            lines.append(f"  {tag:>16} {int(m.sum()):>6}   (too few samples)")
            continue
        lines.append(f"  {tag:>16} {int(m.sum()):>6} {e[m].mean():+9.2f} {e[m].std():9.2f} "
                     f"{np.median(np.abs(e[m])):10.2f}")
    lo_m = (a >= 0) & (a < 30)
    hi_m = (a >= 60)
    if lo_m.sum() >= 10 and hi_m.sum() >= 10:
        gap = e[lo_m].mean() - e[hi_m].mean()
        lines.append(f"  -> along-depth minus across-view bias = {gap:+.2f} mm")
        if abs(gap) < 1.0:
            lines.append("     VERDICT: consistent. No evidence of a focal-length error.")
        elif abs(gap) < 3.0:
            lines.append("     VERDICT: mild disagreement. Worth a second run before acting.")
        else:
            lines.append("     VERDICT: ORIENTATION-DEPENDENT. This is the fx signature.")
    else:
        lines.append("  -> not enough spread: hold the board FACING the cameras for a few")
        lines.append("     positions AND turned edge-on (rotated about vertical) for others.")
    return lines


def summarise(name, errs):
    """Report BIAS and SCATTER separately -- they have different causes and different fixes: bias (signed mean) = systematic geometry/scale error."""
    if not errs:
        return f"{name}: no samples"
    e = np.array(errs, dtype=float)
    a = np.abs(e)
    return (f"{name}: n={len(e)}  bias={e.mean():+.2f}mm  scatter(std)={e.std():.2f}mm  "
            f"|err| mean={a.mean():.2f}mm  median={np.median(a):.2f}mm  max={a.max():.2f}mm")


def main(indices):
    Pmats = load_P(indices)
    intr = load_intrinsics(indices)
    caps = {i: open_camera(i) for i in indices}
    caps = {i: c for i, c in caps.items() if c is not None}
    if len(caps) < 2:
        print("Need >=2 cameras.")
        return
    print(f"Undistorting points for cam(s) {sorted(intr)} before triangulation.")
    print("Move the board to a new spot in the volume, then HOLD IT STILL.")
    print("Frames only count while the board is stationary (the cameras are not")
    print("hardware-synced, so a moving board corrupts the triangulation).")
    print("Sample ~15-20 positions/tilts across the volume. q to stop.")
    all_h, all_v, all_span = [], [], []
    centre = rig_centre(sorted(caps))
    oriented = []
    frames_used = 0
    prev_corners = None
    while True:
        frames = grab_synced(caps)
        corners = {}
        for i, f in frames.items():
            cs = detect(f)
            if cs is not None:
                corners[i] = cs

        shift = max_corner_shift(prev_corners, corners) if prev_corners else float("inf")
        still = shift <= STILL_PX
        prev_corners = corners if corners else None

        if len(corners) >= 2 and still:
            pts3d = triangulate_board(Pmats, undistort_corner_dict(corners, intr))
            h, v = spacing_errors(pts3d)
            all_h += h
            all_v += v
            all_span += [e for _, e in span_errors(pts3d)]
            oriented += oriented_spacings(pts3d, centre)
            frames_used += 1

        disp_tiles = []
        for i, f in frames.items():
            cs = corners.get(i)
            if cs is not None:
                cv2.drawChessboardCorners(f, CHECKERBOARD, cs.reshape(-1, 1, 2), True)
            d = cv2.resize(f, (426, 240))
            cv2.putText(d, f"cam{i} {'OK' if cs is not None else '--'}", (8, 24),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                        (0, 255, 0) if cs is not None else (0, 0, 255), 2)
            disp_tiles.append(d)

        if disp_tiles:
            combined = cv2.hconcat(disp_tiles)
            if len(corners) >= 2:
                state = "STILL - counting" if still else "MOVING - hold steady"
                colour = (0, 255, 0) if still else (0, 165, 255)
            else:
                state = "show board to >=2 cams"
                colour = (0, 0, 255)
            err = (f"   adj-err so far: {np.mean(all_h + all_v):.2f}mm"
                   if (all_h + all_v) else "")
            if oriented:
                _a = np.array([o[1] for o in oriented])
                err += (f"   orient: depth {int((_a < 30).sum())} / "
                        f"across {int((_a >= 60).sum())}")
            cv2.putText(combined, f"frames used: {frames_used}   {state}{err}",
                        (10, combined.shape[0] - 12),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, colour, 2)
            cv2.imshow("board accuracy - move, then HOLD STILL (q to stop)", combined)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    for c in caps.values():
        c.release()
    cv2.destroyAllWindows()

    lines = [
        "=== 3D reconstruction accuracy (checkerboard known-distance test) ===",
        f"cameras: {list(caps)}   frames used: {frames_used}",
        f"known spacings: horizontal {SQUARE_W_MM}mm, vertical {SQUARE_H_MM}mm",
        summarise(f"adjacent-horizontal (vs {SQUARE_W_MM}mm)", all_h),
        summarise(f"adjacent-vertical   (vs {SQUARE_H_MM}mm)", all_v),
        summarise("adjacent-combined", all_h + all_v),
        summarise("full-span (width/height, scale check)", all_span),
    ] + orientation_report(oriented)
    print("\n" + "\n".join(lines))
    os.makedirs("results", exist_ok=True)
    with open("results/board_accuracy.txt", "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\nSaved results/board_accuracy.txt")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python src/triangulate_board_accuracy.py 0 1 2")
        sys.exit(0)
    main([int(a) for a in sys.argv[1:]])
