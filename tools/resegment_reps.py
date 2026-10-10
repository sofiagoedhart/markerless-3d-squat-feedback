"""Re-cut repetition boundaries from a recorded set's pelvis-height trace."""
import argparse
import csv
import glob
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, "src")

import metrics as M
from session_io import load_session_filtered
from analyse_sets import body_frame_from_meta

ENTER_MM = 100.0
EXIT_MM = 40.0
DEPTH_LO, DEPTH_HI = 0.45, 1.60
DUR_LO = 0.40
FAST_DEPTH, FAST_DUR = 1.25, 0.60


def pelvis_trace(path):
    """Finite pelvis heights and their timestamps for one recorded set."""
    frames, meta = load_session_filtered(path, "stored", 1.0, 0.020)
    frame = body_frame_from_meta(meta)
    hs, ts = [], []
    for kp, t in frames:
        v = M.pelvis_height(np.asarray(kp, float), frame)
        if np.isfinite(v):
            hs.append(v)
            ts.append(t)
    return np.asarray(hs), np.asarray(ts), meta


def segment(h, t):
    """Repetition bounds as (start, bottom, end) index triples."""
    stand = np.percentile(h, 90)
    cand, inrep, i0 = [], False, 0
    for i, v in enumerate(h):
        if not inrep and v < stand - ENTER_MM:
            inrep, i0 = True, i
        elif inrep and v > stand - EXIT_MM:
            inrep = False
            cand.append((i0, i))
    if inrep:
        cand.append((i0, len(h) - 1))
    if not cand:
        return [], stand
    dep = np.array([stand - h[a:b + 1].min() for a, b in cand])
    dur = np.array([t[b] - t[a] for a, b in cand])
    md, mu = np.median(dep), np.median(dur)
    keep = []
    for (a, b), d, u in zip(cand, dep, dur):
        clipped = a == 0 or b == len(h) - 1
        if not DEPTH_LO * md < d < DEPTH_HI * md:
            continue
        if u <= DUR_LO * mu and not clipped:
            continue
        if d > FAST_DEPTH * md and u < FAST_DUR * mu:
            continue
        keep.append((a, a + int(np.argmin(h[a:b + 1])), b))
    return keep, stand


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("session", help="directory of recorded .npz sets")
    ap.add_argument("--out", default=None, help="CSV to write (default: session/rep_index.csv)")
    ap.add_argument("--expect", default=None,
                    help="reps you performed per set, as label=n[,label=n...]")
    a = ap.parse_args()

    expect = {}
    if a.expect:
        for item in a.expect.split(","):
            k, _, v = item.partition("=")
            expect[k.strip()] = int(v)

    out_path = a.out or os.path.join(a.session, "rep_index.csv")
    paths = [p for p in sorted(glob.glob(os.path.join(a.session, "*", "*.npz")))
             if "frametimes" not in p]
    rows, flagged = [], []
    for p in paths:
        h, t, meta = pelvis_trace(p)
        if len(h) == 0:
            continue
        reps, stand = segment(h, t)
        label = str(meta.get("label", os.path.basename(p)))
        t0 = t[0]
        for n, (s, bm, e) in enumerate(reps):
            rows.append({
                "set_file": os.path.basename(p), "label": label, "rep_index": n,
                "start_s": round(t[s] - t0, 2), "bottom_s": round(t[bm] - t0, 2),
                "end_s": round(t[e] - t0, 2), "duration_s": round(t[e] - t[s], 2),
                "depth_mm": round(float(stand - h[s:e + 1].min()), 1),
            })
        want = expect.get(label)
        mark = ""
        if want is not None and want != len(reps):
            mark = f"   <<< performed {want}"
            flagged.append(label)
        print(f"  {label:36s} reps={len(reps):3d}{mark}")

    with open(out_path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\n{len(rows)} repetitions across {len(paths)} sets -> {out_path}")
    if flagged:
        print("Check these against the video: " + ", ".join(flagged))


if __name__ == "__main__":
    main()
