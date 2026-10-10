"""Regenerate the 15 Sep depth-fit table (D0, B) from the three fitting sets."""
import os, sys, numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
import analyse_sets as A, rep_engine as RE
base = ROOT + "/recordings/2026-09-15_biomech/20260915_085532/"
rows = {}
for name, lab in (("01_partial_1", "partial"), ("02_parallel_1", "parallel"), ("03_deep_1", "deep")):
    info, reps = A.replay(base + name + ".npz")
    h0 = info["standing"] and np.median([r["h"] for r in info["standing"]])
    for rep in reps:
        b = A.bottom_rows(rep); rp = rep["report"]
        m = A.med([r["depth"] for r in b])
        f = rp.get("femur_mm"); k = RE.depth_scale(f)
        drop = h0 - min(r["h"] for r in rep["rows"]) if h0 else np.nan
        rows.setdefault(lab, []).append((m, m / k, rp.get("knee_at_depth"), drop, f, RE.classify_depth(m, femur_mm=f)))
for lab, v in rows.items():
    a = np.array([[x if x is not None else np.nan for x in r[:5]] for r in v], float)
    print(lab, "n", len(v),
          "margin %.1f±%.1f" % (np.nanmean(a[:,0]), np.nanstd(a[:,0], ddof=1)),
          "norm %.1f±%.1f [%.1f..%.1f]" % (np.nanmean(a[:,1]), np.nanstd(a[:,1], ddof=1), np.nanmin(a[:,1]), np.nanmax(a[:,1])),
          "knee %.1f±%.1f (n=%d)" % (np.nanmean(a[:,2]), np.nanstd(a[:,2], ddof=1), np.isfinite(a[:,2]).sum()),
          "drop %.0f±%.0f" % (np.nanmean(a[:,3]), np.nanstd(a[:,3], ddof=1)),
          "femur %.0f" % np.nanmean(a[:,4]),
          "class", {c: [r[5] for r in v].count(c) for c in set(r[5] for r in v)})
d = [r[1] for r in rows["deep"]]; p = [r[1] for r in rows["parallel"]]; q = [r[1] for r in rows["partial"]]
lo = (max(d) + min(p)) / 2; hi = (max(p) + min(q)) / 2
print("boundaries %.1f %.1f -> D0 %.1f B %.1f" % (lo, hi, (lo + hi) / 2, (hi - lo) / 2))
allr = [r for v in rows.values() for r in v if r[2] is not None and np.isfinite(r[2])]
x = np.array([r[2] for r in allr]); y = np.array([r[0] for r in allr])
s, c = np.polyfit(x, y, 1); print("n", len(x), "margin = %.2f*knee %+.0f  r=%.3f" % (s, c, np.corrcoef(x, y)[0,1]))
