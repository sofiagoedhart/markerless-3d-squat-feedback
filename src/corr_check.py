"""Measure the correlation between repetition depth and the valgus metric, per filter channel."""
import glob, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyse_sets as A

S = "/mnt/user-data/uploads/Skripsie/recordings/2026-08-30_sets"
paths = [p for p in sorted(glob.glob(S + "/*.npz")) if not p.endswith("_frametimes.npz")]

print(f"{'channel':<10}{'n reps':>8}{'r(depth, valgus)':>20}{'slope /100mm':>16}")
print("-" * 56)
for ch in ("stored", "raw", "euro"):
    D, V = [], []
    for p in paths:
        info, reps = A.replay(p, ch)
        for rep in reps:
            rows = A.bottom_rows(rep)
            d = A.med([r["depth"] for r in rows])
            v = A.med([r["vL"] for r in rows] + [r["vR"] for r in rows])
            if d is not None and v is not None and np.isfinite(d) and np.isfinite(v):
                D.append(d); V.append(v)
    D, V = np.array(D), np.array(V)
    r = float(np.corrcoef(D, V)[0, 1])
    slope = float(np.polyfit(D, V, 1)[0]) * 100
    print(f"{ch:<10}{len(D):>8}{r:>20.3f}{slope:>16.3f}")
print()
print("26 Aug reference (old filter, uncorrectable): r = +0.875, slope +0.036/100mm")
print("Positive r = deeper reps read as more valgus, i.e. the metric is measuring")
print("depth as much as knee position.")
