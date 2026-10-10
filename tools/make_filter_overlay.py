"""Draw the pelvis-trajectory overlay comparing raw, Kalman and One Euro output for Section 6 (filtering)."""
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from tune_filter import (load_set, trim_lead_tail, still_mask, run_kalman, run_euro,
                         evaluate, _signal, _interp_nan, _mov_med, L_HIP, R_HIP)

SESSION = "recordings/2026-08-30_sets"
OUT = "thesis_23092026/figures/filter_overlay"
EURO, KAL = (1.0, 0.020), (12, 4.0)
C_RAW, C_KAL, C_EUR, INK = "#E0609E", "#FC7803", "#6DC7F7", "#2B2F36"

plt.rcParams.update({"font.family": "sans-serif",
                     "font.sans-serif": ["Helvetica", "Arial", "DejaVu Sans"],
                     "font.size": 10, "axes.edgecolor": "#9AA3AF", "axes.linewidth": 0.7,
                     "xtick.color": INK, "ytick.color": INK, "axes.labelcolor": INK,
                     "text.color": INK})


def get(sub):
    """Load and trim the first recording whose name contains `sub`."""
    for f in sorted(os.listdir(SESSION)):
        if sub in f and f.endswith(".npz"):
            return trim_lead_tail(load_set(os.path.join(SESSION, f)))[0]
    raise SystemExit(sub)


def pelvis(s, arr):
    """Vertical pelvis trace (mm) of one stream, gaps interpolated."""
    return _interp_nan(_signal(arr, s, [L_HIP, R_HIP], "up"))


fast, static, slow = get("fast"), get("static"), get("slow")
still = still_mask(static)

raw, kal, eur = (pelvis(fast, a) for a in (fast["raw"], run_kalman(fast, *KAL), run_euro(fast, *EURO)))
top = np.percentile(raw, 90)
t = fast["t"] - fast["t"][0]
dt = float(np.median(np.diff(t)))
d_raw = top - raw
lo, hi = int(np.searchsorted(t, 11.0)), int(np.searchsorted(t, 18.9))
ta = t[lo:hi]

w = max(3, int(round(1.0 / float(np.median(np.diff(static["t"]))))) | 1)
tb_all = static["t"] - static["t"][0]
idx = np.flatnonzero(still)
runs = np.split(idx, np.flatnonzero(np.diff(idx) > 1) + 1)
seg = max(runs, key=len)
seg = seg[:int(round(6.0 / float(np.median(np.diff(static["t"])))))]
dev = {}
for name, arr in (("raw", static["raw"]), ("kal", run_kalman(static, *KAL)), ("eur", run_euro(static, *EURO))):
    y = pelvis(static, arr)
    dev[name] = (y - _mov_med(y, w))[seg]
tb = tb_all[seg] - tb_all[seg][0]

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 3.6), gridspec_kw={"width_ratios": [1.35, 1]})

ax1.plot(ta, d_raw[lo:hi], color=C_RAW, lw=0.9, marker="o", ms=2.6, label="Unfiltered")
ax1.plot(ta, (top - kal)[lo:hi], color=C_KAL, lw=1.7, ls=(0, (5, 2)), label="Kalman")
ax1.plot(ta, (top - eur)[lo:hi], color=C_EUR, lw=1.7, label="One Euro")
ax1.set_xlabel("Time in set (s)")
ax1.set_ylabel("Pelvis drop from standing (mm)")
ax1.set_title("(a) Fast squat set", loc="left", fontsize=10.5, fontweight="bold")
ax1.legend(fontsize=9, frameon=False, loc="upper center", ncol=3)
ax1.set_ylim(top=d_raw[lo:hi].max() * 1.22)

ax2.plot(tb, dev["raw"], color=C_RAW, lw=0.9, marker="o", ms=2.3)
ax2.plot(tb, dev["kal"], color=C_KAL, lw=1.7, ls=(0, (5, 2)))
ax2.plot(tb, dev["eur"], color=C_EUR, lw=1.7)
ax2.axhline(0, color="#9AA3AF", lw=0.6)
ax2.set_xlabel("Time (s)")
ax2.set_ylabel("Pelvis vertical residual (mm)")
ax2.set_title("(b) Standing still", loc="left", fontsize=10.5, fontweight="bold")

for ax in (ax1, ax2):
    ax.grid(color="#E3E7EC", lw=0.6)
    ax.set_axisbelow(True)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)

fig.tight_layout()
for ext in ("pdf", "png"):
    fig.savefig(f"{OUT}.{ext}", dpi=300, bbox_inches="tight")

sets = dict(static=static, fast=fast, slow=slow)
for tag, kw in (("Kalman", dict(q=KAL[0], r=KAL[1])), ("One Euro", dict(euro=EURO))):
    e = evaluate(sets, still=still, **kw)
    print(f"{tag}: resid {e['static_resid_mm']:.2f} mm, delay fast {e['fast_delay_ms']:.0f} ms, slow {e['slow_delay_ms']:.0f} ms")
print("standing frames:", int(still.sum()), "| window a:", round(ta[-1], 1), "s | window b:", round(tb[-1], 1), "s")
