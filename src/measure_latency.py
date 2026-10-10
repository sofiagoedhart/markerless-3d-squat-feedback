"""Measure where the live delay comes from: camera backlog, pipeline and filter."""
from __future__ import annotations
import argparse
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

FAST_MS = 8.0
CAM_FPS = 30.0


def filter_delay(path):
    from session_io import load_session_arrays
    A = load_session_arrays(path)
    kp, raw, t = A["kp"], A["kp_raw"], A["t"]
    if raw is None:
        sys.exit(f"{path} has no kp_raw channel -- recorded before 30 Aug 2026.")
    dt = float(np.median(np.diff(t)))
    T, J, _ = kp.shape
    print(f"\n{os.path.basename(path)}: {T} frames at {1/dt:.1f} fps "
          f"({1000*dt:.0f} ms per frame)")

    shifts = np.arange(0, 7)
    per_joint = []
    for j in range(J):
        errs = []
        for s in shifts:
            a = kp[s:, j, :]
            b = raw[:T - s if s else T, j, :]
            m = np.all(np.isfinite(a), 1) & np.all(np.isfinite(b), 1)
            errs.append(np.mean(np.sum((a[m] - b[m]) ** 2, 1)) if m.sum() > 20
                        else np.inf)
        errs = np.asarray(errs)
        i = int(np.argmin(errs))
        if not np.isfinite(errs[i]):
            continue
        if 0 < i < len(shifts) - 1 and np.all(np.isfinite(errs[i-1:i+2])):
            a0, b0, c0 = errs[i-1], errs[i], errs[i+1]
            denom = (a0 - 2 * b0 + c0)
            frac = 0.5 * (a0 - c0) / denom if denom != 0 else 0.0
            per_joint.append(i + float(np.clip(frac, -0.5, 0.5)))
        else:
            per_joint.append(float(i))
    d = np.asarray(per_joint)
    print(f"  Kalman equivalent group delay: median {np.median(d):.2f} frames "
          f"= {1000 * dt * np.median(d):.0f} ms   "
          f"(p90 {np.percentile(d, 90):.2f} fr = "
          f"{1000 * dt * np.percentile(d, 90):.0f} ms)")
    both = np.all(np.isfinite(kp), 2) & np.all(np.isfinite(raw), 2)
    if both.any():
        e = np.linalg.norm(kp - raw, axis=2)[both]
        print(f"  displacement filtered vs raw: median {np.median(e):.0f} mm, "
              f"p90 {np.percentile(e, 90):.0f} mm")
    return float(1000 * dt * np.median(d))


def backlog(caps, order, rounds=3):
    """Count frames already sitting in each camera's queue."""
    print("\nCamera queue backlog (stale frames waiting to be read):")
    worst = 0.0
    for i in order:
        counts = []
        for _ in range(rounds):
            n = 0
            for _ in range(12):
                t0 = time.time()
                caps[i].grab()
                if (time.time() - t0) * 1000.0 > FAST_MS:
                    break
                n += 1
            counts.append(n)
            time.sleep(0.4)
        m = float(np.median(counts))
        ms = 1000.0 * m / CAM_FPS
        worst = max(worst, ms)
        flag = "  << this is pure latency" if m >= 2 else ""
        print(f"  cam{i}: {counts} stale frames (median {m:.0f}) "
              f"= {ms:.0f} ms behind live{flag}")
    return worst


def stage_costs(model, caps, order, indices, rig, device, n=15):
    from live_form_feedback import grab
    from kalman_smoother import SkeletonKalman
    kal = SkeletonKalman()
    print(f"\nPipeline cost per iteration (median of {n}):")
    ts, prev = [], None
    for _ in range(n):
        t0 = time.time()
        sm3d, frames, valid, t, dt = grab(model, caps, order, indices, rig,
                                          kal, device, prev)
        prev = t
        ts.append((time.time() - t0) * 1000.0)
    ts = np.asarray(ts)
    print(f"  full grab->3D iteration: median {np.median(ts):.0f} ms "
          f"(p90 {np.percentile(ts, 90):.0f} ms) = {1000/np.median(ts):.1f} fps")
    return float(np.median(ts))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("indices", nargs="*", type=int)
    ap.add_argument("--from-recording", default=None)
    ap.add_argument("--model", default="yolo11n-pose.pt")
    a = ap.parse_args()

    if a.from_recording:
        filter_delay(a.from_recording)
        return
    if not a.indices:
        sys.exit("give camera indices (e.g. 0 1 2) or --from-recording <npz>")

    from ultralytics import YOLO
    from live_triangulate import load_rig, open_camera, pick_device

    rig = load_rig(a.indices)
    device = pick_device()
    model = YOLO(a.model)
    caps, order = {}, []
    for i in a.indices:
        c = open_camera(i)
        if c is None:
            print(f"!! cam{i} would not open")
            continue
        caps[i], _ = c, order.append(i)
    if not order:
        sys.exit("no cameras opened")

    print("\nWarming up (the queue must reach its steady state first)...")
    t0 = time.time()
    while time.time() - t0 < 3.0:
        for i in order:
            caps[i].grab()
        for i in order:
            caps[i].retrieve()
        time.sleep(0.13)

    q_ms = backlog(caps, order)
    loop_ms = stage_costs(model, caps, order, a.indices, rig, device)
    for c in caps.values():
        c.release()

    print("\n" + "=" * 62)
    print("END-TO-END BUDGET (what you see minus what you did):")
    print(f"  camera queue backlog      {q_ms:6.0f} ms   <- fixed by --drain")
    print(f"  one pipeline iteration    {loop_ms:6.0f} ms   <- model / resolution")
    print(f"  Kalman group delay        see --from-recording")
    print(f"  Unity smoothing           ~1 packet interval at smoothing=0.3")
    print("=" * 62)


if __name__ == "__main__":
    main()
