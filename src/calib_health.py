"""Start-of-session check for whether the rig has been knocked since it was calibrated."""

import os
import sys
import re
import json
import time

import numpy as np
import cv2
try:
    import viz
except Exception:
    pass

from dlt_triangulation import project, triangulate_point_dlt
from triangulate_board_accuracy import (
    open_camera, load_P, detect, triangulate_board, spacing_errors, CHECKERBOARD,
    grab_synced, max_corner_shift, STILL_PX,
    load_intrinsics, undistort_corner_dict,
)

TARGET_FRAMES = 15
TIMEOUT_SEC = 45
MIN_FRAMES = 5

BASELINE_PATH = "calib/health_baseline.json"

KNOCK_RATIO = 2.5
KNOCK_ABS_PX = 4.0
WATCH_RATIO = 1.6
WATCH_ABS_PX = 2.0

SANITY_CEILING_PX = 25.0


def read_health_baseline():
    """{cam: loo_px} recorded at a calibration we trusted, or None."""
    try:
        with open(BASELINE_PATH) as f:
            d = json.load(f)
        return {int(k): float(v) for k, v in d["loo_px"].items()}
    except Exception:
        return None


def write_health_baseline(per_cam):
    os.makedirs("calib", exist_ok=True)
    with open(BASELINE_PATH, "w") as f:
        json.dump({"loo_px": {str(k): round(v, 3) for k, v in per_cam.items()},
                   "note": "per-camera leave-one-out reprojection right after a "
                           "trusted calibration; calib_health compares against this"},
                  f, indent=2)
    print(f"\nSaved {BASELINE_PATH}:")
    for i in sorted(per_cam):
        print(f"    cam{i}  {per_cam[i]:.1f} px")
    print("  Future runs flag a camera that drifts away from ITS OWN value here.")
    print("  Re-run with --set-baseline after any recalibration.")


def read_baseline():
    """Adjacent-combined median (mm) from the last board test, if present."""
    try:
        with open("results/board_accuracy.txt") as f:
            m = re.search(r"adjacent-combined:.*?median=([\d.]+)mm", f.read())
        if m:
            return float(m.group(1))
    except Exception:
        pass
    return None


def loo_reproj(Pmats, corners):
    """Leave-one-out reprojection per camera."""
    ids = list(corners)
    if len(ids) < 3:
        return None
    n = corners[ids[0]].shape[0]
    res = {i: [] for i in ids}
    for j in range(n):
        for i in ids:
            others = [c for c in ids if c != i]
            X = triangulate_point_dlt([Pmats[c] for c in others],
                                      [corners[c][j] for c in others])
            res[i].append(float(np.linalg.norm(project(Pmats[i], X) - corners[i][j])))
    return {i: float(np.median(res[i])) for i in ids}


def main(indices, set_baseline=False):
    if not os.path.exists("calib/extrinsics.json"):
        print("calib/extrinsics.json not found — run this from the Skripsie repo root.")
        return

    Pmats = load_P(indices)
    intr = load_intrinsics(indices)
    caps = {i: open_camera(i) for i in indices}
    caps = {i: c for i, c in caps.items() if c is not None}
    if len(caps) < 2:
        print("Need at least 2 cameras open.")
        return
    missing = [i for i in caps if i not in intr]
    if missing:
        print(f"!! No intrinsics for cam{missing} — those points stay DISTORTED, so the")
        print("   reprojection numbers below will be inflated. Don't trust the verdict.")

    baseline = read_baseline()
    have3 = len(caps) >= 3
    print("Calibration health check.")
    if have3:
        print("Stand the board so ALL THREE cameras see it (centre of the volume),")
        print("then LEAVE IT STILL — only stationary frames count. Hands off.")
    else:
        print("Only 2 cameras — scale check only (a knock needs 3 cams; use live_triangulate.py).")
    if baseline is not None:
        print(f"Baseline (last board test): adjacent median {baseline:.2f} mm")

    loo_acc = {i: [] for i in caps}
    adj = []
    good3 = good_any = 0
    moving_frames = 0
    prev_corners = None
    t0 = time.time()

    while good3 < TARGET_FRAMES and (time.time() - t0) < TIMEOUT_SEC:
        frames = grab_synced(caps)
        corners = {}
        for i, f in frames.items():
            cs = detect(f)
            if cs is not None:
                corners[i] = cs

        shift = max_corner_shift(prev_corners, corners) if prev_corners else float("inf")
        still = shift <= STILL_PX
        prev_corners = corners if corners else None
        if len(corners) >= 2 and not still:
            moving_frames += 1

        ucorners = undistort_corner_dict(corners, intr) if corners else {}

        if len(corners) >= 2 and still:
            h, v = spacing_errors(triangulate_board(Pmats, ucorners))
            adj += h + v
            good_any += 1
        if len(corners) >= 3 and still:
            L = loo_reproj(Pmats, ucorners)
            if L:
                for i in L:
                    loo_acc[i].append(L[i])
                good3 += 1

        tiles = []
        for i, f in frames.items():
            cs = corners.get(i)
            if cs is not None:
                cv2.drawChessboardCorners(f, CHECKERBOARD, cs.reshape(-1, 1, 2), True)
            d = cv2.resize(f, (426, 240))
            cv2.putText(d, f"cam{i} {'OK' if cs is not None else '--'}", (8, 24),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                        (0, 255, 0) if cs is not None else (0, 0, 255), 2)
            tiles.append(d)

        if tiles:
            combined = cv2.hconcat(tiles)
            if len(corners) < 3:
                state, colour = "show board to 3 cams", (0, 0, 255)
            elif not still:
                state, colour = f"MOVING ({shift:.1f}px) - hold still", (0, 165, 255)
            else:
                worst = max((np.median(v) for v in loo_acc.values() if v), default=None)
                state = f"STILL - worst reproj {worst:.1f}px" if worst is not None else "STILL"
                colour = (0, 255, 0)
            cv2.putText(combined, f"frames {good3}/{TARGET_FRAMES}   {state}",
                        (10, combined.shape[0] - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.6, colour, 2)
            cv2.imshow("calibration health check - HOLD BOARD STILL (q to stop)", combined)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    for c in caps.values():
        c.release()
    cv2.destroyAllWindows()

    adj_med = float(np.median(np.abs(adj))) if adj else float("nan")
    adj_bias = float(np.mean(adj)) if adj else float("nan")
    base_txt = f" vs baseline {baseline:.2f}mm" if baseline is not None else ""

    print("\n=== calibration health ===")
    print(f"still frames used: {good3}   (rejected while moving: {moving_frames})")
    if adj:
        print(f"adjacent spacing : median |err| {adj_med:.2f} mm{base_txt}   "
              f"bias {adj_bias:+.2f} mm   (scale sanity)")

    per_cam = {i: float(np.median(v)) for i, v in loo_acc.items() if v}
    if good3 >= MIN_FRAMES and per_cam:
        base = read_health_baseline()

        if set_baseline:
            line = "   ".join(f"cam{i} {per_cam[i]:.1f}px" for i in sorted(per_cam))
            print(f"reprojection     : {line}")
            write_health_baseline(per_cam)
            return

        if base is None:
            line = "   ".join(f"cam{i} {per_cam[i]:.1f}px" for i in sorted(per_cam))
            print(f"reprojection     : {line}   (no baseline recorded)")
            print()
            worst = max(per_cam.values())
            if worst > SANITY_CEILING_PX:
                print(f"[!]   Something is badly wrong — worst {worst:.1f}px. Check the")
                print("      green skeleton in live_triangulate.py before trusting anything.")
            else:
                print("[?]   No baseline to compare against, so this can't tell you whether")
                print("      anything has MOVED — these absolute numbers are geometry-dependent")
                print(f"      and {worst:.1f}px may be perfectly healthy for this rig.")
                print("      Right after a calibration you trust, run:")
                print("          python src/calib_health.py 0 1 2 --set-baseline")
            return

        print("reprojection     : " + "   ".join(
            f"cam{i} {per_cam[i]:.1f}px (base {base.get(i, float('nan')):.1f})"
            for i in sorted(per_cam)))
        print()
        knocked, watch = [], []
        for i, cur in per_cam.items():
            b = base.get(i)
            if b is None:
                continue
            rise, ratio = cur - b, cur / max(b, 0.1)
            if ratio >= KNOCK_RATIO and rise >= KNOCK_ABS_PX:
                knocked.append((i, cur, b))
            elif ratio >= WATCH_RATIO and rise >= WATCH_ABS_PX:
                watch.append((i, cur, b))

        if knocked:
            names = ", ".join(f"cam{i} ({b:.1f} -> {c:.1f}px)" for i, c, b in knocked)
            print(f"[!]   RECALIBRATE — moved away from baseline: {names}")
            print("      Run 'python src/live_triangulate.py 0 1 2' to confirm which view's")
            print("      green skeleton is offset, then recapture and recalibrate.")
        elif watch:
            names = ", ".join(f"cam{i} ({b:.1f} -> {c:.1f}px)" for i, c, b in watch)
            print(f"[~]   Drifting a little: {names}. Re-run; if it persists, recalibrate.")
        else:
            print("[OK]  Calibration intact — every camera is in line with its baseline.")
            print("      Good to go.")
        return

    if good_any >= MIN_FRAMES and adj:
        print(f"\n[scale only] {good_any} two-camera frames — scale looks "
              f"{'fine' if adj_med < max(2.0, 3*(baseline or 1)) else 'off'} "
              f"({adj_med:.2f}mm), but this does NOT detect a knock.")
        print("For the knock check, position the board so all 3 cameras see it, or eyeball")
        print("live_triangulate.py (offset green skeleton in one view = that camera moved).")
    elif moving_frames > good3:
        print(f"\nOnly {good3} STILL three-camera frame(s) — {moving_frames} were rejected for movement.")
        print("Prop the board on a stand/chair so it is completely stationary, then rerun.")
    else:
        print(f"\nOnly {good3} three-camera frame(s) — hold the board so all 3 cameras see it and rerun.")


if __name__ == "__main__":
    args = sys.argv[1:]
    set_baseline = "--set-baseline" in args
    idxs = [int(a) for a in args if not a.startswith("--")] or [0, 1, 2]
    main(idxs, set_baseline=set_baseline)
