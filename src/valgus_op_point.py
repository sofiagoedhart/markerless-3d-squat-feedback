"""Find the best usable threshold for each valgus candidate."""
import sys, numpy as np
sys.path.insert(0, ".")
from valgus_bakeoff import gather, build_candidates, auc, UP26, UP30

r26 = gather(UP26, "stored")
r30 = gather(UP30, "euro")
c26, c30 = build_candidates(r26, "_asc"), build_candidates(r30, "_asc")
cond26 = np.array([r["cond"] for r in r26])
cond30 = np.array([r["cond"] for r in r30])

print(f"{'candidate':<32}{'AUC in/norm':>13}{'best thresh':>13}"
      f"{'hit IN':>10}{'FP norm':>10}{'OUT fired':>11}")
print("-" * 89)
for k in c26:
    v26, v30 = c26[k], c30[k]
    IN = np.concatenate([v26[cond26 == "IN"], v30[cond30 == "IN"]])
    NO = np.concatenate([v26[cond26 == "NORMAL"], v30[cond30 == "NORMAL"]])
    OUT = v26[cond26 == "OUT"]
    IN, NO, OUT = (x[np.isfinite(x)] for x in (IN, NO, OUT))
    a = auc(IN, NO)
    best = None
    for th in np.unique(np.concatenate([IN, NO])):
        fp = (NO > th).mean()
        if fp <= 0.10:
            hit = (IN > th).mean()
            if best is None or hit > best[1]:
                best = (th, hit, fp, (OUT > th).mean() if len(OUT) else np.nan)
    if best is None:
        print(f"{k:<32}{a:>13.2f}{'  no threshold under 10% FP':>45}")
        continue
    th, hit, fp, o = best
    print(f"{k:<32}{a:>13.2f}{th:>13.3f}{hit:>9.0%}{fp:>10.0%}{o:>11.0%}")
print()
print(f"n: IN {len(IN)} reps (both sessions), NORMAL {len(NO)}, OUT {len(OUT)}")
print("OUT fired = knees deliberately pushed OUTWARD that the cue wrongly flags.")
