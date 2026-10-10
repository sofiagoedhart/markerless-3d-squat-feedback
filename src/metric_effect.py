"""Measure what each filter setting does to the reported depth and knee angle."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import metrics as M
from tune_filter import (load_set, trim_lead_tail, still_mask,
                         run_kalman, run_euro, _signal, _interp_nan,
                         L_HIP, R_HIP)

SESSION = sys.argv[1] if len(sys.argv) > 1 else "recordings/2026-08-30_sets"


def rep_bottoms(sig, dt, min_prom=80.0):
    """Frame index of each rep bottom in a pelvis-height trace."""
    w = max(2, int(round(0.5 / dt)))
    out = []
    for i in range(w, len(sig) - w):
        seg = sig[i - w:i + w + 1]
        if sig[i] == seg.min() and (seg.max() - seg.min()) > min_prom:
            if not out or i - out[-1] > w:
                out.append(i)
    return out


def knee_sd_deg(arr, mask, w=9):
    """Jitter of the knee angle while stationary."""
    vals = np.full(len(arr), np.nan)
    for i in range(len(arr)):
        v = M.knee_signal(arr[i])
        if v is not None and np.isfinite(v):
            vals[i] = v
    med = np.full(len(vals), np.nan)
    for i in range(len(vals)):
        seg = vals[max(0, i - w // 2):i + w // 2 + 1]
        seg = seg[np.isfinite(seg)]
        if seg.size:
            med[i] = np.median(seg)
    resid = (vals - med)[mask]
    resid = resid[np.isfinite(resid)]
    return float(np.std(resid)) if len(resid) > 5 else np.nan


CONFIGS = [
    ("raw (no filter)",            None),
    ("Kalman q=12  r=4.0  SHIPPING", ("k", 12, 4.0)),
    ("Kalman q=100 r=4.0",         ("k", 100, 4.0)),
    ("Kalman q=400 r=4.0",         ("k", 400, 4.0)),
    ("Kalman q=1600 r=4.0",        ("k", 1600, 4.0)),
    ("OneEuro mc=0.5 beta=0.002",  ("e", 0.5, 0.002)),
    ("OneEuro mc=0.8 beta=0.004",  ("e", 0.8, 0.004)),
    ("OneEuro mc=1.0 beta=0.007",  ("e", 1.0, 0.007)),
    ("OneEuro mc=1.0 beta=0.020",  ("e", 1.0, 0.020)),
    ("OneEuro mc=1.2 beta=0.012",  ("e", 1.2, 0.012)),
]

files = sorted(f for f in os.listdir(SESSION)
               if f.endswith(".npz") and "frametimes" not in f)
sets = {}
for f in files:
    s, _ = trim_lead_tail(load_set(os.path.join(SESSION, f)))
    sets[f] = s

static = next(v for k, v in sets.items() if "static" in k)
still = still_mask(static)
rep_sets = {k: v for k, v in sets.items()
            if any(x in k for x in ("fast", "slow", "parallel_bar", "deep"))}

print("=" * 82)
print("EFFECT ON THE REPORTED METRICS   (ground truth = the raw stream)")
print("=" * 82)
print(f"rep sets scored: {', '.join(sorted(k[:22] for k in rep_sets))}")
print()
hdr = (f"{'configuration':<30}{'depth bias':>13}{'worst rep':>11}"
       f"{'knee sd (still)':>17}")
print(hdr)
print("-" * len(hdr))

raw_depths = {}
for name, cfg in CONFIGS:
    biases = []
    for k, s in rep_sets.items():
        dt = float(np.median(np.diff(s["t"])))
        rs = _interp_nan(_signal(s["raw"], s, [L_HIP, R_HIP], "up"))
        if cfg is None:
            arr = s["raw"]
        elif cfg[0] == "k":
            arr = run_kalman(s, cfg[1], cfg[2])
        else:
            arr = run_euro(s, cfg[1], cfg[2])
        fs = _interp_nan(_signal(arr, s, [L_HIP, R_HIP], "up"))

        if k not in raw_depths:
            raw_depths[k] = rep_bottoms(rs, dt)
        top = np.percentile(rs, 90)
        for b in raw_depths[k]:
            lo, hi = max(0, b - 3), min(len(rs), b + 4)
            d_raw = top - rs[lo:hi].min()
            d_fil = top - fs[lo:hi].min()
            biases.append(d_fil - d_raw)

    if cfg is None:
        arrs = static["raw"]
    elif cfg[0] == "k":
        arrs = run_kalman(static, cfg[1], cfg[2])
    else:
        arrs = run_euro(static, cfg[1], cfg[2])
    ksd = knee_sd_deg(arrs, still)

    b = np.array(biases)
    print(f"{name:<30}{np.mean(b):>10.1f} mm{np.min(b):>8.1f} mm"
          f"{ksd:>14.2f} deg   (n={len(b)} reps)")

print()
print("depth bias: filtered rep depth minus raw rep depth. NEGATIVE = the")
print("            filter reports the squat SHALLOWER than it was measured.")
print("knee sd   : jitter of the knee interior angle while standing still.")
