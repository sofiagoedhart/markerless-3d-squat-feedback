"""Draw the filter-comparison figure used in the thesis."""
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tune_filter import (load_set, trim_lead_tail, still_mask, run_kalman,
                         run_euro, evaluate, _signal, _interp_nan,
                         L_HIP, R_HIP)

SESSION = sys.argv[1] if len(sys.argv) > 1 else "recordings/2026-08-30_sets"
OUT = "results"
EURO = (1.0, 0.020)
os.makedirs(OUT, exist_ok=True)


def get(sub):
    for f in sorted(os.listdir(SESSION)):
        if sub in f and f.endswith(".npz") and "frametimes" not in f:
            return trim_lead_tail(load_set(os.path.join(SESSION, f)))[0]
    raise SystemExit(sub)


fast = get("fast")
static = get("static")
slow = get("slow")
sets = dict(static=static, fast=fast, slow=slow)
still = still_mask(static)

dt = float(np.median(np.diff(fast["t"])))
raw_s = _interp_nan(_signal(fast["raw"], fast, [L_HIP, R_HIP], "up"))
kal = _interp_nan(_signal(run_kalman(fast, 12, 4.0), fast, [L_HIP, R_HIP], "up"))
eur = _interp_nan(_signal(run_euro(fast, *EURO), fast, [L_HIP, R_HIP], "up"))

top = np.percentile(raw_s, 90)
raw_d, kal_d, eur_d = top - raw_s, top - kal, top - eur

w = int(round(2.0 / dt))
b = int(np.argmax(raw_d[w:len(raw_d) - w])) + w
lo, hi = max(0, b - w), min(len(raw_d), b + w)
tt = (fast["t"][lo:hi] - fast["t"][b])

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.6, 3.6))

ax1.plot(tt, raw_d[lo:hi], color="0.15", lw=1.0, ls="-", marker="o", ms=3.0,
         label="raw (triangulated)")
ax1.plot(tt, kal_d[lo:hi], color="0.45", lw=1.6, ls="--",
         label="Kalman $q$=12, $r$=4.0 (as shipped)")
ax1.plot(tt, eur_d[lo:hi], color="0.0", lw=1.6, ls="-.",
         label=f"One Euro $f_{{c,\\min}}$={EURO[0]}, $\\beta$={EURO[1]}")
ax1.axhline(raw_d[lo:hi].max(), color="0.7", lw=0.8, ls=":")
ax1.annotate("", xy=(0.35, raw_d[lo:hi].max()), xytext=(0.35, kal_d[lo:hi].max()),
             arrowprops=dict(arrowstyle="<->", lw=0.9, color="0.3"))
ax1.text(0.42, 0.5 * (raw_d[lo:hi].max() + kal_d[lo:hi].max()),
         f"{raw_d[lo:hi].max() - kal_d[lo:hi].max():.0f} mm\nunder-read",
         fontsize=7.5, va="center", color="0.25")
ax1.set_xlabel("time about the bottom of the rep (s)")
ax1.set_ylabel("hip depth below standing (mm)")
ax1.set_title("(a) one fast rep, same data, three filters", fontsize=9.5, loc="left")
ax1.legend(fontsize=7.2, frameon=True, framealpha=0.9,
           edgecolor="none", loc="upper left")
ax1.set_ylim(top=raw_d[lo:hi].max() * 1.30)
ax1.grid(alpha=0.25, lw=0.5)

qs = [1, 4, 8, 12, 25, 50, 100, 200, 400, 800, 1600, 3200]
delay, over = [], []
for q in qs:
    e = evaluate(sets, q=q, r=4.0, still=still)
    delay.append(e["fast_delay_ms"])
    over.append(abs(e["fast_overshoot_mm"]))

ee = evaluate(sets, euro=EURO, still=still)

ax2.plot(delay, over, color="0.15", lw=1.2, marker="o", ms=3.5,
         label="constant-velocity Kalman,\n$q$ from 1 to 3200")
for q, d, o in zip(qs, delay, over):
    if q in (12, 50, 100, 400, 3200):
        off = (6, -10) if q in (50, 3200) else (6, 5)
        ax2.annotate(f"$q$={q}", (d, o), textcoords="offset points",
                     xytext=off, fontsize=7.2, color="0.3")
ax2.plot([ee["fast_delay_ms"]], [abs(ee["fast_overshoot_mm"])], marker="*",
         ms=13, color="0.0", ls="none", label="One Euro (chosen)")
ax2.set_xlabel("group delay on the fast set (ms)")
ax2.set_ylabel("|depth error at the turnaround| (mm)")
ax2.set_xlim(left=-15)
ax2.set_ylim(bottom=-3)
ax2.set_title("(b) the trade-off, and a filter that is not on it",
              fontsize=9.5, loc="left")
ax2.legend(fontsize=7.2, frameon=False)
ax2.grid(alpha=0.25, lw=0.5)

fig.tight_layout()
for ext in ("pdf", "png"):
    fig.savefig(os.path.join(OUT, f"filter_choice.{ext}"), dpi=200,
                bbox_inches="tight")
print("wrote", os.path.join(OUT, "filter_choice.pdf/.png"))
print(f"panel (a) under-read on this rep: "
      f"{raw_d[lo:hi].max() - kal_d[lo:hi].max():.1f} mm")
print(f"One Euro point: {ee['fast_delay_ms']:.0f} ms, "
      f"{abs(ee['fast_overshoot_mm']):.1f} mm")
