"""Check the extrinsic calibration by reconstructing a known real-world length."""

import os
import sys
import json
import time

import numpy as np
import cv2
try:
    import viz
except Exception:
    pass

from multiview_triangulate import Camera, triangulate_joint
from dlt_triangulation import project
from triangulate_board_accuracy import load_intrinsics, undistort_points

CAP_WIDTH, CAP_HEIGHT = 1280, 720
WIN = "known-distance check"


def load_rig(indices):
    """Build a Camera per index from calib/extrinsics.json (same as live_triangulate)."""
    data = json.load(open("calib/extrinsics.json"))
    cams = data["cameras"]
    rig, order = [], []
    for i in indices:
        if str(i) not in cams:
            print(f"  cam{i} not in extrinsics.json (has {list(cams)}) — skipping.")
            continue
        c = cams[str(i)]
        rig.append(Camera(np.array(c["K"]), np.array(c["R"]),
                          np.array(c["t"]), name=f"cam{i}"))
        order.append(i)
    print(f"Loaded {len(rig)} cameras from calib/extrinsics.json "
          f"(units: {data.get('units', 'mm')}).")
    return rig, order


def open_camera(index):
    cap = cv2.VideoCapture(index, cv2.CAP_AVFOUNDATION)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAP_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAP_HEIGHT)
    for _ in range(45):
        ok, f = cap.read()
        if ok and f is not None and f.mean() > 5:
            return cap
        time.sleep(0.03)
    return None


def grab_fresh(cap):
    """Read a few frames so we get a current (not buffered) image."""
    f = None
    for _ in range(5):
        ok, fr = cap.read()
        if ok and fr is not None:
            f = fr
    return f


def click_two_points(img, cam_name):
    """Show img and let the user click END A then END B."""
    state = {"pts": []}

    def redraw():
        d = img.copy()
        for k, p in enumerate(state["pts"]):
            cv2.circle(d, tuple(p), 6, (0, 255, 0), -1)
            cv2.putText(d, "AB"[k], (p[0] + 9, p[1] - 9),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        if len(state["pts"]) == 2:
            cv2.line(d, tuple(state["pts"][0]), tuple(state["pts"][1]), (0, 255, 0), 2)
        cv2.putText(d, f"{cam_name}:  click END A then END B",
                    (10, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 255), 2)
        cv2.putText(d, "r=reset   s=skip (not visible)   ENTER=next   Esc=quit",
                    (10, 52), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 2)
        cv2.imshow(WIN, d)

    def on_mouse(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN and len(state["pts"]) < 2:
            state["pts"].append([x, y])
            redraw()

    cv2.namedWindow(WIN)
    cv2.setMouseCallback(WIN, on_mouse)
    redraw()
    while True:
        k = cv2.waitKey(20) & 0xFF
        if k == ord("r"):
            state["pts"] = []
            redraw()
        elif k == ord("s"):
            return None
        elif k == 27:
            return "QUIT"
        elif k in (13, 10, ord(" ")) and len(state["pts"]) == 2:
            return (np.array(state["pts"][0], float),
                    np.array(state["pts"][1], float))


def reproj_residuals(rig, X, pts, used):
    """Pixel distance between each used view's click and the reprojected 3D point."""
    return [float(np.linalg.norm(project(rig[i].P, X) - np.asarray(pts[i])))
            for i in used]


def measure_once(rig, order, caps, known_mm, intr=None):
    """One placement: click both ends in each view, triangulate, report."""
    intr = intr or {}
    frames = {i: grab_fresh(caps[i]) for i in order}

    A_pts, B_pts, A_conf, B_conf = [], [], [], []
    for cam_i in order:
        img = frames[cam_i]
        if img is None:
            A_pts.append(None); B_pts.append(None); A_conf.append(0.0); B_conf.append(0.0)
            continue
        res = click_two_points(img, f"cam{cam_i}")
        if res == "QUIT":
            cv2.destroyWindow(WIN)
            return "QUIT"
        if res is None:
            A_pts.append(None); B_pts.append(None); A_conf.append(0.0); B_conf.append(0.0)
        else:
            a, b = res
            if cam_i in intr:
                K, dist = intr[cam_i]
                a, b = undistort_points([a, b], K, dist)
            A_pts.append(a); B_pts.append(b); A_conf.append(1.0); B_conf.append(1.0)
    cv2.destroyWindow(WIN)

    n_used = int(sum(c > 0 for c in A_conf))
    if n_used < 2:
        print(f"  Only {n_used} camera(s) saw the tape — need >=2. Skipping this placement.")
        return None

    XA, usedA = triangulate_joint(rig, A_pts, A_conf, conf_thresh=0.5, min_views=2)
    XB, usedB = triangulate_joint(rig, B_pts, B_conf, conf_thresh=0.5, min_views=2)
    if XA is None or XB is None:
        print("  Triangulation failed for one end (too few views). Skipping.")
        return None

    dist = float(np.linalg.norm(XA - XB))
    err = dist - known_mm
    pct = 100.0 * err / known_mm
    rA = reproj_residuals(rig, XA, A_pts, usedA)
    rB = reproj_residuals(rig, XB, B_pts, usedB)

    print("\n  --- result ---")
    print(f"  End A  {np.round(XA, 1)} mm   views {[order[i] for i in usedA]}   "
          f"reproj {np.round(rA, 1)} px")
    print(f"  End B  {np.round(XB, 1)} mm   views {[order[i] for i in usedB]}   "
          f"reproj {np.round(rB, 1)} px")
    print(f"  measured length : {dist:8.1f} mm")
    print(f"  known length    : {known_mm:8.1f} mm")
    print(f"  error           : {err:+8.1f} mm   ({pct:+.2f} %)")
    if max(rA + rB) > 3.0:
        print("  note: a reprojection residual > 3 px means that click didn't land where the")
        print("        3D point projects back — re-click more precisely, or that view may be off.")
    return abs(pct), err, dist


def verdict(med_pct):
    print("\n  Verdict:")
    if med_pct < 1.0:
        print(f"  [OK]   {med_pct:.2f}% median error — extrinsics look solid. No need to recalibrate.")
    elif med_pct < 2.0:
        print(f"  [~]    {med_pct:.2f}% median error — usable and fine for form work.")
        print("         Recalibrate only if you want tighter scale; check no camera was bumped.")
    else:
        print(f"  [!]    {med_pct:.2f}% median error — larger than expected.")
        print("         Check whether a camera moved: run live_triangulate.py — if the green")
        print("         skeleton is offset in ONE view, that camera drifted. Then re-run")
        print("         calibrate_extrinsics.py.")


def main(known_mm, indices):
    if not os.path.exists("calib/extrinsics.json"):
        print("calib/extrinsics.json not found — run this from the Skripsie repo root.")
        return

    rig, order = load_rig(indices)
    intr = load_intrinsics(indices)
    if len(rig) < 2:
        print("Need at least 2 calibrated cameras in extrinsics.json.")
        return

    kept_rig, kept_order, caps = [], [], {}
    for cam, i in zip(rig, order):
        cap = open_camera(i)
        if cap is None:
            print(f"  cam{i} did not open — skipping.")
            continue
        caps[i] = cap
        kept_rig.append(cam)
        kept_order.append(i)
    rig, order = kept_rig, kept_order
    if len(rig) < 2:
        print("Need at least 2 cameras open.")
        return

    print(f"\nKnown length = {known_mm:.1f} mm.")
    print("Lay the tape in the volume, visible to >=2 cameras. Ideally test a few")
    print("placements: near where you stand, and out toward the edges of the volume.\n")

    print("Tag each placement with where in the volume the object is lying, so the")
    print("per-position summary below fills Table 6.4 without transcribing by hand.\n")

    results, tag = [], "centre"
    try:
        while True:
            ans = input(f"  position [{tag}] (centre/left/right/near/far, "
                        f"ENTER keeps it, q quits)\n"
                        f"  -- the camera views open once you answer: ").strip().lower()
            if ans == "q":
                break
            if ans:
                tag = ans
            r = measure_once(rig, order, caps, known_mm, intr)
            if r == "QUIT":
                break
            if r is not None:
                results.append((tag,) + r)
                done = sum(1 for x in results if x[0] == tag)
                print(f"  ({done} placement(s) recorded at '{tag}')")
    finally:
        for cap in caps.values():
            cap.release()
        cv2.destroyAllWindows()

    if results:
        pcts = np.array([r[1] for r in results])
        print("\n==================== SUMMARY ====================")
        print(f"placements measured : {len(results)}")
        print(f"|error| %  ->  mean {pcts.mean():.2f}   median {np.median(pcts):.2f}   "
              f"max {pcts.max():.2f}")

        print("\nPER POSITION  (Table 6.4):")
        print(f"  {'position':<10}{'n':>3}{'mean |err| mm':>15}{'SD mm':>9}"
              f"{'mean |err| %':>14}")
        order_seen = []
        for t, _, _, _ in results:
            if t not in order_seen:
                order_seen.append(t)
        for t in order_seen:
            e = np.array([abs(r[2]) for r in results if r[0] == t])
            q = np.array([r[1] for r in results if r[0] == t])
            print(f"  {t:<10}{len(e):>3}{e.mean():>15.1f}"
                  f"{(e.std(ddof=1) if len(e) > 1 else float('nan')):>9.1f}"
                  f"{q.mean():>14.2f}")
        all_mm = np.array([abs(r[2]) for r in results])
        print(f"  {'ALL':<10}{len(all_mm):>3}{all_mm.mean():>15.1f}"
              f"{(all_mm.std(ddof=1) if len(all_mm) > 1 else float('nan')):>9.1f}"
              f"{pcts.mean():>14.2f}")

        out = os.path.join("results", "known_distance.csv")
        os.makedirs("results", exist_ok=True)
        new_file = not os.path.exists(out)
        with open(out, "a") as fh:
            if new_file:
                fh.write("position,abs_error_pct,error_mm,measured_mm,known_mm\n")
            for t, q, e, d in results:
                fh.write(f"{t},{q:.4f},{e:.2f},{d:.2f},{known_mm:.1f}\n")
        print(f"\nappended {len(results)} placements to {out}")

        verdict(float(np.median(pcts)))
        print("=================================================")
    else:
        print("\nNo valid placements measured.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python src/check_known_distance.py <known_length_mm> [cam indices]")
        print("   e.g. python src/check_known_distance.py 1000 0 1 2")
        sys.exit(0)
    known = float(sys.argv[1])
    idxs = [int(a) for a in sys.argv[2:]] or [0, 1, 2]
    main(known, idxs)
