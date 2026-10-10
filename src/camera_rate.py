"""What frame rate are the cameras actually delivering, and how long does a fresh frame cost?"""
import argparse, sys, os, time
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cv2
from live_form_feedback import open_camera

FAST_MS = 8.0


def probe(cap, n=60):
    """Walk to the live edge, then time n fresh grabs."""
    for _ in range(12):
        t0 = time.perf_counter()
        cap.grab()
        if (time.perf_counter() - t0) * 1000.0 > FAST_MS:
            break
    gaps = []
    for _ in range(n):
        t0 = time.perf_counter()
        cap.grab()
        gaps.append((time.perf_counter() - t0) * 1000.0)
    return np.asarray(gaps)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("indices", nargs="+", type=int)
    a = ap.parse_args()
    print("Cameras must be free — stop live_form_feedback first.\n")
    caps = {}
    for i in a.indices:
        c = open_camera(i)
        if c is None:
            sys.exit(f"cam{i} would not open")
        caps[i] = c
    print(f"{'cam':>4}  {'driver says':>12}  {'measured':>9}  {'per frame':>10}  {'p90':>7}")
    rates = []
    for i in a.indices:
        g = probe(caps[i])
        med = float(np.median(g))
        fps = 1000.0 / med
        rates.append(fps)
        try:
            said = caps[i].get(cv2.CAP_PROP_FPS)
        except Exception:
            said = float("nan")
        print(f"{i:>4}  {said:>9.1f} fps  {fps:>6.1f} fps  {med:>7.1f} ms  "
              f"{np.percentile(g, 90):>5.1f} ms")
    for c in caps.values():
        c.release()
    slowest = min(rates)
    print(f"\nSlowest camera delivers {slowest:.1f} fps.")
    print(f"The loop cannot exceed that, and --cam-fps should be {slowest:.0f}, "
          "not 30, or the drain asks for frames that have not arrived yet.")
    if slowest < 25:
        print("Well under 30 — auto-exposure has almost certainly lengthened "
              "in this light. Note the room lighting in the test log.")


if __name__ == "__main__":
    main()
