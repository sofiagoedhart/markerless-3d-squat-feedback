"""Score candidate knee-position measures against the deliberate valgus conditions."""
import glob
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import metrics as M
import analyse_sets as A

UP26 = "recordings/20260826_134109"
UP30 = "recordings/2026-08-30_sets"


def fppa(kp, frame, side):
    """Frontal-plane projection angle at the knee, in degrees."""
    idx = {"L": (M.L_HIP, M.L_KNE, M.L_ANK), "R": (M.R_HIP, M.R_KNE, M.R_ANK)}[side]
    H, K, An = kp[idx[0]], kp[idx[1]], kp[idx[2]]
    if not all(np.all(np.isfinite(p)) for p in (H, K, An)):
        return np.nan
    f = lambda p: np.array([float(np.dot(p, frame.lateral)),
                            float(np.dot(p, frame.up))])
    h, k, a = f(H), f(K), f(An)
    v1, v2 = h - k, a - k
    n1, n2 = np.linalg.norm(v1), np.linalg.norm(v2)
    if n1 < 1e-6 or n2 < 1e-6:
        return np.nan
    ang = np.degrees(np.arccos(np.clip(np.dot(v1, v2) / (n1 * n2), -1, 1)))
    d = a - h
    cross = d[0] * (k[1] - h[1]) - d[1] * (k[0] - h[0])
    medial = -cross if side == "L" else cross
    return float((180.0 - ang) * np.sign(medial if medial != 0 else 1.0))


def per_frame(kp, frame):
    """Every candidate's raw per-frame value, plus what bottom_rows needs."""
    return dict(
        h=M.pelvis_height(kp, frame),
        knee=M.knee_signal(kp),
        depth=M.depth_margin(kp, frame),
        m1L=M.knee_valgus_norm(kp, frame, "L"),
        m1R=M.knee_valgus_norm(kp, frame, "R"),
        m2L=fppa(kp, frame, "L"),
        m2R=fppa(kp, frame, "R"),
        m3=M.knee_ankle_sep_ratio(kp, frame),
    )


def cohen_d(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    a, b = a[np.isfinite(a)], b[np.isfinite(b)]
    if len(a) < 2 or len(b) < 2:
        return np.nan
    s = np.sqrt(((len(a) - 1) * a.var(ddof=1) + (len(b) - 1) * b.var(ddof=1))
                / (len(a) + len(b) - 2))
    return float((a.mean() - b.mean()) / s) if s > 1e-12 else np.nan


def auc(pos, neg):
    """P(a random pos scores above a random neg)."""
    pos, neg = np.asarray(pos, float), np.asarray(neg, float)
    pos, neg = pos[np.isfinite(pos)], neg[np.isfinite(neg)]
    if not len(pos) or not len(neg):
        return np.nan
    w = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return float(w / (len(pos) * len(neg)))


MEAS = ("m1L", "m1R", "m2L", "m2R", "m3")


def replay_all(path, channel):
    """Analyse_sets.replay, but carrying every candidate measure per frame."""
    from session_io import load_session_filtered, body_frame_from_meta
    import rep_engine as RE

    frames, meta = load_session_filtered(path, channel)
    frame = body_frame_from_meta(meta)
    if frame is None:
        raise SystemExit(f"{path}: no body_frame in meta")
    eng = RE.SquatRepEngine(frame, target=meta.get("target", "parallel"),
                            theta0=meta.get("theta0_deg"), h0=meta.get("h0_mm"))
    reps, buf, seen = [], [], False
    for kp, t in frames:
        kp = np.asarray(kp, float)
        row = per_frame(kp, frame)
        st = eng.update(kp, t)
        row["phase"] = st["phase"]
        if st["phase"] != "SETUP":
            buf.append(row)
        if st["rep_completed"]:
            seen = True
            reps.append({"rows": buf, "report": st["last_rep"]})
            buf = []
        elif st["phase"] == "SETUP":
            buf = []
    return meta, reps


def condition_of(label):
    """NORMAL / IN / OUT from the set label."""
    l = label.lower()
    if "valgusout" in l:
        return "OUT"
    if "valgusin" in l:
        return "IN"
    return "NORMAL"


def gather(session, channel):
    """-> list of per-rep dicts: condition, depth, and each candidate."""
    paths = [p for p in sorted(glob.glob(os.path.join(session, "*.npz")))
             if not p.endswith("_frametimes.npz")]
    out = []
    for p in paths:
        meta, reps = replay_all(p, channel)
        cond = condition_of(meta.get("label", os.path.basename(p)))
        for rep in reps:
            bot = A.bottom_rows(rep)
            if not bot:
                continue
            top = rep["rows"][:3]
            asc = [r for r in rep["rows"] if r.get("phase") == "ASCENT"]
            g = lambda k, rows: A.med([r.get(k) for r in rows])
            rec = dict(cond=cond, set=os.path.basename(p)[:30],
                       depth=g("depth", bot))
            for k in MEAS:
                rec[k] = g(k, bot)
                rec[k + "_asc"] = g(k, asc) if asc else np.nan
                rec[k + "_pk"] = (float(np.nanmax([r.get(k, np.nan)
                                                   for r in rep["rows"]]))
                                  if rep["rows"] else np.nan)
                rec[k + "_top"] = g(k, top)
            for suf in ("", "_asc", "_pk"):
                for tag in ("m1", "m2"):
                    v = [rec.get(tag + "L" + suf), rec.get(tag + "R" + suf)]
                    v = [x for x in v if x is not None and np.isfinite(x)]
                    rec[tag + "_worst" + suf] = max(v) if v else np.nan
                rec["m3_worst" + suf] = rec.get("m3" + suf, np.nan)
            out.append(rec)
    return out


def residualise(reps, key, fit_on=("NORMAL",)):
    """Regress `key` on depth using only `fit_on` reps, and return the residual for every rep."""
    d = np.array([r["depth"] for r in reps], float)
    v = np.array([r.get(key, np.nan) for r in reps], float)
    m = np.array([r["cond"] in fit_on for r in reps])
    ok = m & np.isfinite(d) & np.isfinite(v)
    if ok.sum() < 3:
        return np.full(len(reps), np.nan)
    b, a = np.polyfit(d[ok], v[ok], 1)
    return v - (a + b * d)


def build_candidates(reps, w=""):
    """Candidates evaluated in window `w`: "" = bottom, "_asc" = ascent."""
    arr = lambda k: np.array([r.get(k, np.nan) for r in reps], float)
    c = {}
    c["M1 valgus_norm (worst knee)"] = arr("m1_worst"+w)
    c["M2 FPPA deg (worst knee)"] = arr("m2_worst"+w)
    c["M3 -KASR (bilateral)"] = -arr("m3_worst"+w)
    c["M4 valgus_norm | depth"] = residualise(reps, "m1_worst"+w)
    c["M5 valgus_norm, rep-self-ref"] = arr("m1_worst"+w) - np.array(
        [np.nanmax([r.get("m1L_top", np.nan), r.get("m1R_top", np.nan)])
         for r in reps], float)
    c["M6 -KASR | depth"] = -residualise(reps, "m3_worst"+w)
    c["M7 FPPA | depth"] = residualise(reps, "m2_worst"+w)
    return c


def report(name, reps, out, w=""):
    conds = [r["cond"] for r in reps]
    depth = np.array([r["depth"] for r in reps], float)
    cand = build_candidates(reps, w)
    idx = lambda c: [i for i, x in enumerate(conds) if x == c]
    iIN, iOUT, iNORM = idx("IN"), idx("OUT"), idx("NORMAL")

    out("")
    out("=" * 78)
    out(f"{name}  [{ {'':'BOTTOM window','_asc':'ASCENT window'}[w] }]   —   {len(reps)} reps   "
        f"(NORMAL {len(iNORM)}, IN {len(iIN)}, OUT {len(iOUT)})")
    out("=" * 78)
    if iIN and iOUT:
        out(f"depth match IN vs OUT: {np.nanmedian(depth[iIN]):.1f} mm vs "
            f"{np.nanmedian(depth[iOUT]):.1f} mm")
    out("")
    hdr = (f"{'candidate':<32}{'|r| depth':>10}{'IN vs OUT':>20}"
           f"{'IN vs NORMAL':>20}")
    out(hdr)
    out(f"{'':<32}{'':>10}{'d      AUC':>20}{'d      AUC':>20}")
    out("-" * len(hdr))
    for k, v in cand.items():
        ok = np.isfinite(v) & np.isfinite(depth)
        r = abs(np.corrcoef(depth[ok], v[ok])[0, 1]) if ok.sum() > 3 else np.nan
        if iIN and iOUT:
            d1, a1 = cohen_d(v[iIN], v[iOUT]), auc(v[iIN], v[iOUT])
            s1 = f"{d1:6.2f} {a1:7.2f}"
        else:
            s1 = f"{'--':>14}"
        if iIN and iNORM:
            d2, a2 = cohen_d(v[iIN], v[iNORM]), auc(v[iIN], v[iNORM])
            s2 = f"{d2:6.2f} {a2:7.2f}"
        else:
            s2 = f"{'--':>14}"
        out(f"{k:<32}{r:>10.3f}{s1:>20}{s2:>20}")
    return cand


def side_gain(reps, out, w=""):
    """Does each knee respond to the deliberate change, or only one of them?"""
    conds = [r["cond"] for r in reps]
    idx = lambda c: [i for i, x in enumerate(conds) if x == c]
    iIN, iOUT = idx("IN"), idx("OUT")
    if not (iIN and iOUT):
        return
    out("")
    win = {"": "BOTTOM", "_asc": "ASCENT"}[w]
    out(f"LEFT/RIGHT GAIN, {win} window  (IN minus OUT — a usable safety cue")
    out("must respond on BOTH legs, not just the one the cameras see best)")
    out(f"{'measure':<20}{'LEFT gain':>12}{'d':>7}{'AUC':>7}"
        f"{'RIGHT gain':>13}{'d':>7}{'AUC':>7}")
    out("-" * 73)
    for tag, kL, kR in (("valgus_norm", "m1L", "m1R"), ("FPPA deg", "m2L", "m2R")):
        row = f"{tag:<20}"
        for k in (kL, kR):
            v = np.array([r.get(k + w, np.nan) for r in reps], float)
            gain = np.nanmedian(v[iIN]) - np.nanmedian(v[iOUT])
            row += (f"{gain:>12.3f}{cohen_d(v[iIN], v[iOUT]):>7.1f}"
                    f"{auc(v[iIN], v[iOUT]):>7.2f}")
        out(row)


def sweep(r26, r30, out, key="m1_worst_asc"):
    """A concrete operating point for the winning candidate: what threshold, and what would it flag?"""
    out("")
    out("=" * 78)
    out(f"OPERATING POINT — {key}, the ascent window")
    out("=" * 78)
    out(f"{'threshold':>10}{'26 Aug IN':>12}{'26 Aug OUT':>12}"
        f"{'26 Aug NORM':>13}{'30 Aug IN':>12}{'30 Aug NORM':>13}")
    out("-" * 72)
    g = lambda reps, c: np.array([r.get(key, np.nan) for r in reps
                                  if r["cond"] == c], float)
    sets = [g(r26, "IN"), g(r26, "OUT"), g(r26, "NORMAL"),
            g(r30, "IN"), g(r30, "NORMAL")]
    for th in (-0.06, -0.04, -0.02, 0.0, 0.01, 0.02, 0.03, 0.04, 0.06):
        cells = "".join(
            f"{int(np.nansum(v > th))}/{int(np.isfinite(v).sum())}".rjust(w)
            for v, w in zip(sets, (12, 12, 13, 12, 13)))
        out(f"{th:>10.2f}{cells}")
    out("")
    out("Want: high IN, low OUT, low NORMAL. OUT is the adversarial case —")
    out("knees deliberately pushed the WRONG way must never fire the cue.")


def main():
    lines = []
    def out(s=""):
        print(s)
        lines.append(s)

    out("#" * 78)
    out("# VALGUS BAKE-OFF — can any knee-position geometry separate the conditions?")
    out("#" * 78)

    r26 = gather(UP26, "stored")
    r30 = gather(UP30, "euro")
    for w in ("", "_asc"):
        report("26 Aug  (stored channel — no kp_raw for this session)", r26, out, w)
        report("30 Aug  (euro channel, corrected filter)", r30, out, w)
    side_gain(r26, out, "")
    side_gain(r26, out, "_asc")
    sweep(r26, r30, out)

    out("")
    out("=" * 78)
    out("READING THIS")
    out("=" * 78)
    out("|r| depth : how much of the measure is just depth. M1 fails here.")
    out("d         : Cohen's d. |d| > 0.8 is a large effect; sign follows the")
    out("            direction the condition was performed in.")
    out("AUC       : P(a random IN rep scores above a random OUT/NORMAL rep).")
    out("            1.00 = the two conditions never overlap, 0.50 = chance.")
    out("            With n this small, AUC is the more trustworthy column.")
    with open("results/valgus_bakeoff.txt", "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\nwrote results/valgus_bakeoff.txt")


if __name__ == "__main__":
    main()
