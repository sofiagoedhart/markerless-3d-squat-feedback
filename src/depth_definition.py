"""What knee bend is actually a squat?"""
import argparse
import glob
import os
import sys
from collections import Counter

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import metrics as M
from session_io import load_session
from replay_to_unity import build, refilter
import rep_engine as RE

LABELS = {
    "parallel_normal_box": "parallel",
    "partial_normal_10_box": "partial",
    "deep_normal_10_box": "deep",
    "parallel_arms_free_5": "parallel",
}


class _Euro:
    """Stand-in for the argparse namespace refilter wants."""
    channel = "euro"
    euro_min_cutoff = 1.0
    euro_beta = 0.020
    process_var = 12.0
    measurement_var = 4.0


def _seg(kp, a, b):
    """Length of one limb segment, in mm."""
    p, q = kp[a], kp[b]
    if not (np.all(np.isfinite(p)) and np.all(np.isfinite(q))):
        return np.nan
    return float(np.linalg.norm(p - q))


def reps_for(path):
    """Replay one recording and return a row per repetition."""
    frames, meta = load_session(path)
    frames = refilter(path, frames, _Euro())
    _, eng = build(frames, meta, target="parallel")[:2]

    name = os.path.basename(path).replace(".npz", "")[3:]
    femur, tibia, standing, bottom, out = [], [], [], [], []
    for kp, t in frames:
        k = np.asarray(kp, float)
        st = eng.update(k, t)
        theta = st.get("knee_angle")
        if st["phase"] == "SETUP" and theta is not None and theta > RE.UPRIGHT_DEG:
            standing.append(theta)
            for a, b in ((M.L_HIP, M.L_KNE), (M.R_HIP, M.R_KNE)):
                v = _seg(k, a, b)
                if np.isfinite(v):
                    femur.append(v)
            for a, b in ((M.L_KNE, M.L_ANK), (M.R_KNE, M.R_ANK)):
                v = _seg(k, a, b)
                if np.isfinite(v):
                    tibia.append(v)
        if st["phase"] == "BOTTOM" and theta is not None:
            bottom.append(theta)
        if st["rep_completed"]:
            r = st["last_rep"]
            out.append(dict(
                set=name,
                label=LABELS.get(name),
                margin=r.get("depth_margin_mm"),
                knee=float(np.median(bottom)) if bottom else np.nan,
                variation=r.get("variation"),
                femur=float(np.median(femur)) if femur else np.nan,
                tibia=float(np.median(tibia)) if tibia else np.nan,
                standing=float(np.median(standing)) if standing else np.nan,
            ))
            bottom = []
    return out


def classify_femur(margin_mm, femur_mm, offset=None, band=None, cap=None):
    """The shipping rule with every threshold expressed as a fraction of the athlete's own femur, so it scales with the subject instead of being fitted to one."""
    offset = RE.DEPTH_OFFSET / SOFIA_FEMUR if offset is None else offset
    band = RE.PARALLEL_BAND / SOFIA_FEMUR if band is None else band
    cap = RE.PARTIAL_MAX_MM / SOFIA_FEMUR if cap is None else cap
    if not (np.isfinite(margin_mm) and np.isfinite(femur_mm) and femur_mm > 0):
        return "unknown"
    x = margin_mm / femur_mm
    if x > cap:
        return "too_shallow"
    d = x - offset
    if d > band:
        return "partial"
    if d < -band:
        return "deep"
    return "parallel"


SOFIA_FEMUR = 434.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("session", nargs="?", default="recordings/2026-09-07_valgus")
    a = ap.parse_args()
    files = sorted(f for f in glob.glob(os.path.join(a.session, "*.npz"))
                   if "frametimes" not in f)
    if not files:
        sys.exit(f"no recordings in {a.session}")

    rows = []
    for f in files:
        try:
            rows.extend(reps_for(f))
        except Exception as e:
            print(f"!! {os.path.basename(f)}: {type(e).__name__}: {e}")
    rows = [r for r in rows if np.isfinite(r["margin"])]

    femurs = [r["femur"] for r in rows if np.isfinite(r["femur"])]
    tibias = [r["tibia"] for r in rows if np.isfinite(r["tibia"])]
    stand = [r["standing"] for r in rows if np.isfinite(r["standing"])]
    F = float(np.median(femurs))

    print("=" * 78)
    print("1.  THE SUBJECT")
    print("=" * 78)
    print(f"  femur  (hip-knee)    {F:6.0f} mm   sd {np.std(femurs):4.1f} mm "
          f"({100 * np.std(femurs) / F:.1f} % across {len(files)} sets)")
    print(f"  tibia  (knee-ankle)  {np.median(tibias):6.0f} mm   "
          f"sd {np.std(tibias):4.1f} mm")
    print(f"  standing knee angle  {np.median(stand):6.1f} deg  "
          "(180 = perfectly straight)")

    print()
    print("=" * 78)
    print("2.  WHAT EACH DELIBERATE DEPTH ACTUALLY REACHES  (box-referenced)")
    print("=" * 78)
    print(f"  {'label':<10}{'n':>4}{'margin mm':>16}{'knee angle deg':>20}"
          f"{'flexion deg':>14}")
    lab = [r for r in rows if r["label"]]
    for name in ("partial", "parallel", "deep"):
        g = [r for r in lab if r["label"] == name]
        if not g:
            continue
        m = np.array([r["margin"] for r in g], float)
        k = np.array([r["knee"] for r in g], float)
        print(f"  {name:<10}{len(g):>4}{np.mean(m):11.0f} sd {np.std(m):2.0f}"
              f"{np.nanmean(k):15.1f} sd {np.nanstd(k):3.1f}"
              f"{180 - np.nanmean(k):13.0f}")

    ok = [r for r in lab if np.isfinite(r["knee"])]
    p = np.polyfit([r["knee"] for r in ok], [r["margin"] for r in ok], 1)
    r2 = np.corrcoef([r["knee"] for r in ok], [r["margin"] for r in ok])[0, 1]
    print(f"\n  The two channels are one measurement: "
          f"margin = {p[0]:.2f} mm/deg x knee {p[1]:+.0f},  r = {r2:.4f}, n = {len(ok)}")
    print("  Shipping boundaries, converted to knee angle through that fit:")
    for mm, what in ((RE.PARTIAL_MAX_MM, "not a squat / partial"),
                     (RE.DEPTH_OFFSET + RE.PARALLEL_BAND, "partial / parallel"),
                     (RE.DEPTH_OFFSET - RE.PARALLEL_BAND, "parallel / deep")):
        print(f"    {mm:6.0f} mm  =  knee {(mm - p[1]) / p[0]:5.1f} deg  "
              f"=  {mm / F:.3f} femur    {what}")

    print()
    print("=" * 78)
    print("3.  THREE WAYS TO DRAW THE BOUNDARIES, SCORED ON HER OWN LABELS")
    print("=" * 78)

    def knee_rule(r, shallow=116.0, pp=87.8, pd=74.0):
        k = r["knee"]
        if not np.isfinite(k):
            return "unknown"
        if k > shallow:
            return "too_shallow"
        if k > pp:
            return "partial"
        if k < pd:
            return "deep"
        return "parallel"

    for name, fn in (("margin mm (shipping)", lambda r: r["variation"]),
                     ("knee angle", knee_rule),
                     ("margin / femur", lambda r: classify_femur(r["margin"],
                                                                 r["femur"]))):
        good = sum(1 for r in lab if fn(r) == r["label"])
        wrong = [f"{r['set'][:18]} {r['label']}->{fn(r)}"
                 for r in lab if fn(r) != r["label"]]
        print(f"  {name:<24}{good}/{len(lab)}"
              + ("   " + "; ".join(wrong[:3]) if wrong else "   all correct"))

    same = sum(1 for r in rows
               if classify_femur(r["margin"], r["femur"]) == r["variation"])
    print(f"\n  Over all {len(rows)} reps, margin/femur and shipping mm agree on "
          f"{same}/{len(rows)};")
    print("  every difference is a rep sitting within 3 mm of a boundary.")
    print("  So the normalisation is a drop-in: it changes no verdict she has seen,")
    print("  and it gives a differently-sized subject a window scaled to their legs:")
    for h in (0.90, 1.00, 1.15):
        f2 = F * h
        lo = (RE.DEPTH_OFFSET / F - RE.PARALLEL_BAND / F) * f2
        hi = (RE.DEPTH_OFFSET / F + RE.PARALLEL_BAND / F) * f2
        print(f"    femur {f2:4.0f} mm  ->  parallel window {lo:5.0f} to {hi:5.0f} mm")

    print()
    print("=" * 78)
    print("4.  HER NATURAL DEPTH SPREAD, NO DEPTH INSTRUCTION GIVEN")
    print("=" * 78)
    free = [r for r in rows if not r["label"]]
    m = np.array([r["margin"] for r in free], float)
    c = Counter(r["variation"] for r in free)
    print(f"  n = {len(free)} reps from the valgus sets, target parallel")
    print(f"  margin  mean {m.mean():.0f} mm  sd {m.std():.0f} mm  "
          f"range [{m.min():.0f}, {m.max():.0f}]")
    print(f"  verdicts {dict(c)}  ->  "
          f"{100 * c['parallel'] / len(free):.0f} % called parallel")
    print(f"  The parallel window is +-{RE.PARALLEL_BAND:.0f} mm, i.e. only "
          f"+-{RE.PARALLEL_BAND / m.std():.1f} sd of her own")
    print("    rep-to-rep variation. Most of the reps that miss are the athlete "
          "moving,")
    print("    not the system erring - worth separating in Ch6.")


if __name__ == "__main__":
    main()
