"""Where does a bend stop being a squat?"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import metrics as M
import rep_engine as RE
import synthetic_squat as S
from replay_to_unity import build


def run(fraction):
    """One session holding a single rep that reaches `fraction` of the way from standing to a full partial squat."""
    bottom = {k: S.STAND[k] + (S.BOTTOMS["partial"][k] - S.STAND[k]) * fraction
              for k in S.STAND}
    saved = S.BOTTOMS.get("_sweep")
    S.BOTTOMS["_sweep"] = bottom
    try:
        frames = S.make_session(reps=("_sweep",), dropout=False)
    finally:
        if saved is None:
            S.BOTTOMS.pop("_sweep", None)
        else:
            S.BOTTOMS["_sweep"] = saved

    _, eng = build(frames, {}, target="parallel")[:2]
    rep, knee_lo, standing = None, np.inf, []
    for kp, t in frames:
        k = np.asarray(kp, float)
        st = eng.update(k, t)
        th = st.get("knee_angle")
        if th is not None and np.isfinite(th):
            if st["phase"] == "SETUP":
                standing.append(th)
            else:
                knee_lo = min(knee_lo, th)
        if st["rep_completed"]:
            rep = st["last_rep"]
    th0 = float(np.median(standing)) if standing else np.nan
    return rep, knee_lo, th0


def main():
    print("A single rep, swept from a token bend to a full partial squat.")
    print("`travel` is how far the knee moved from standing - the quantity")
    print(f"MIN_KNEE_EXCURSION = {RE.MIN_KNEE_EXCURSION:.0f} deg gates on.\n")
    print(f"{'% of a partial':>15}{'knee at bottom':>16}{'travel':>9}"
          f"{'margin mm':>11}{'detected':>10}   verdict")
    print("-" * 78)
    prev = None
    for frac in np.arange(0.15, 1.01, 0.05):
        rep, knee_lo, th0 = run(float(frac))
        travel = th0 - knee_lo if np.isfinite(knee_lo) else np.nan
        if rep is None:
            print(f"{100 * frac:14.0f}%{knee_lo:15.1f}{travel:9.1f}"
                  f"{'-':>11}{'no':>10}   not a repetition")
            verdict = None
        else:
            verdict = rep["variation"]
            flag = "  <-- becomes a squat" if prev in (None, "too_shallow") \
                and verdict != "too_shallow" else ""
            print(f"{100 * frac:14.0f}%{knee_lo:15.1f}{travel:9.1f}"
                  f"{rep['depth_margin_mm']:11.0f}{'yes':>10}   {verdict}{flag}")
        prev = verdict
    print(f"\nThresholds in force: MIN_KNEE_EXCURSION {RE.MIN_KNEE_EXCURSION:.0f} deg, "
          f"PARTIAL_MAX_MM {RE.PARTIAL_MAX_MM:.0f} mm")
    print("The synthetic body is not the subject's, so read the BOUNDARY BEHAVIOUR "
          "here,\n  not the millimetres - her own numbers are in "
          "results/depth_definition.txt.")


if __name__ == "__main__":
    main()
