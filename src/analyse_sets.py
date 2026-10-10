"""Fit and check the assessment thresholds against a labelled recording session."""
from __future__ import annotations
import argparse
import glob
import json
import os
import sys

import numpy as np

import metrics as M
import rep_engine as RE
from session_io import (load_session, load_session_filtered,
                        body_frame_from_meta)


def stance_of(label: str) -> str:
    """The deliberate knee condition a set was captured under, from its label."""
    l = label.lower()
    if "valgusout" in l:
        return "OUT"
    if "valgusin" in l:
        return "IN"
    return "NORMAL"


def depth_of(label: str) -> str:
    """The deliberate depth a set was captured at, from its label."""
    l = label.lower()
    for name in ("qpartial", "partial", "parallel", "deep"):
        if name in l:
            return "partial" if name == "qpartial" else name
    return "?"


def replay(path, channel="stored", min_cutoff=1.0, beta=0.020):
    """Run one recorded set through the engine and return (info, reps)."""
    frames, meta = load_session_filtered(path, channel, min_cutoff, beta)
    frame = body_frame_from_meta(meta)
    if frame is None:
        raise SystemExit(f"{path}: no body_frame in meta -- cannot replay faithfully")

    label = meta.get("label", os.path.basename(path))
    theta0, h0 = meta.get("theta0_deg"), meta.get("h0_mm")

    eng = RE.SquatRepEngine(frame, target=meta.get("target", "parallel"),
                            theta0=theta0, h0=h0)

    standing, reps, buf = [], [], []
    seen_rep = False

    for kp, t in frames:
        kp = np.asarray(kp, float)
        row = {
            "t": t,
            "h": M.pelvis_height(kp, frame),
            "knee": M.knee_signal(kp),
            "depth": M.depth_margin(kp, frame),
            "devL": M.knee_medial_deviation(kp, frame, "L"),
            "devR": M.knee_medial_deviation(kp, frame, "R"),
            "vL": M.knee_valgus_norm(kp, frame, "L"),
            "vR": M.knee_valgus_norm(kp, frame, "R"),
            "sym": M.knee_symmetry(kp),
            "tilt": M.shoulder_tilt(kp, frame),
        }
        st = eng.update(kp, t)
        row["phase"] = st["phase"]

        if (not seen_rep and st["phase"] == "SETUP"
                and np.isfinite(row["knee"]) and row["knee"] > 160.0):
            standing.append(row)

        if st["phase"] != "SETUP":
            buf.append(row)
        if st["rep_completed"]:
            seen_rep = True
            reps.append({"rows": buf, "report": st["last_rep"]})
            buf = []
        elif st["phase"] == "SETUP" and not st["rep_completed"]:
            buf = []

    info = {
        "path": path,
        "label": label,
        "target": meta.get("target"),
        "stance": stance_of(label),
        "depth_label": depth_of(label),
        "n_frames": len(frames),
        "duration": frames[-1][1] - frames[0][1] if frames else 0.0,
        "reps_live": meta.get("reps_detected"),
        "standing": standing,
        "calib": meta.get("calibration", {}),
    }
    return info, reps


def med(vals):
    v = [x for x in vals if x is not None and np.isfinite(x)]
    return float(np.median(v)) if v else np.nan


def bottom_rows(rep, band=RE.DWELL_BAND):
    """Frames within `band` mm of the lowest pelvis position of the rep."""
    hs = [r["h"] for r in rep["rows"] if np.isfinite(r["h"])]
    if not hs:
        return []
    lo = min(hs)
    return [r for r in rep["rows"] if np.isfinite(r["h"]) and abs(r["h"] - lo) < band]


def flexed_rows(rep, gate=RE.FLEXION_GATE_DEG):
    """Frames past the flexion gate -- the only ones the engine trusts for valgus."""
    return [r for r in rep["rows"]
            if np.isfinite(r["knee"]) and r["knee"] < gate]


def fmt(x, nd=1, width=6):
    if x is None or not np.isfinite(x):
        return f"{'--':>{width}}"
    return f"{x:>{width}.{nd}f}"


def section_overview(sets, out):
    out("=" * 78)
    out("1.  SETS REPLAYED")
    out("=" * 78)
    out(f"{'set':34s} {'cond':7s} {'depth':9s} {'frames':>6s} {'dur':>6s} "
        f"{'live':>5s} {'now':>4s}")
    for info, reps in sets:
        out(f"{info['label'][:34]:34s} {info['stance']:7s} {info['depth_label']:9s} "
            f"{info['n_frames']:6d} {info['duration']:6.1f} "
            f"{str(info['reps_live']):>5s} {len(reps):4d}")
    live = sum((i['reps_live'] or 0) for i, _ in sets)
    now = sum(len(r) for _, r in sets)
    out("")
    out(f"total reps: {live} detected live, {now} on replay.")
    if live != now:
        out("  !! MISMATCH -- the engine has changed since capture (the 27 Aug rewrite).")
        out("     The replay numbers are the current engine's; the live ones are historical.")
    hashes = {json.dumps(i["calib"], sort_keys=True) for i, _ in sets}
    out(f"calibration: {'single set of hashes across all sets -- comparable' if len(hashes) == 1 else '!! SETS SPAN DIFFERENT CALIBRATIONS -- not comparable'}")
    out("")


def section_standing(sets, out):
    out("=" * 78)
    out("2.  STANDING NEUTRAL  (per-side offset for neutral referencing)")
    out("=" * 78)
    out("Median over upright frames before the first rep of each set.")
    out("A persistent one-sided reading while standing normally is calibration/keypoint")
    out("bias, not the knee -- that is exactly what the offset removes.")
    out("")
    out(f"{'set':34s} {'n':>4s} {'devL_mm':>8s} {'devR_mm':>8s} {'L-R':>7s} "
        f"{'normL':>7s} {'normR':>7s}")
    allL, allR = [], []
    for info, _ in sets:
        s = info["standing"]
        dL, dR = med([r["devL"] for r in s]), med([r["devR"] for r in s])
        nL, nR = med([r["vL"] for r in s]), med([r["vR"] for r in s])
        gap = dL - dR if (np.isfinite(dL) and np.isfinite(dR)) else np.nan
        out(f"{info['label'][:34]:34s} {len(s):4d} {fmt(dL, 1, 8)} {fmt(dR, 1, 8)} "
            f"{fmt(gap, 1, 7)} {fmt(nL, 3, 7)} {fmt(nR, 3, 7)}")
        if np.isfinite(nL):
            allL.append(nL)
        if np.isfinite(nR):
            allR.append(nR)
    offL, offR = med(allL), med(allR)
    out("")
    out(f"SESSION OFFSET (normalised):  L {offL:+.3f}   R {offR:+.3f}   "
        f"asymmetry {offL - offR:+.3f}")
    out("Zero the ASYMMETRY only. Both knees tracking out at depth is real squat")
    out("mechanics; flattening the shared component would erase it.")
    out("")
    return offL, offR


def section_valgus(sets, offL, offR, out):
    out("=" * 78)
    out("3.  VALGUS VERDICT  (OPEN 2 -- does the metric work at all?)")
    out("=" * 78)
    out("Per rep, the median normalised deviation over the bottom window, and the peak")
    out("over the flexed portion. Positive = knee toward the midline = valgus.")
    out("'ref' columns are neutral-referenced: raw minus this session's standing offset.")
    out("")
    by_cond = {}
    for info, reps in sets:
        out(f"-- {info['label']}   [{info['stance']}]")
        out(f"   {'rep':>3s} {'botL':>7s} {'botR':>7s} {'refL':>7s} {'refR':>7s} "
            f"{'pkL':>7s} {'pkR':>7s} {'susL_s':>7s} {'susR_s':>7s}")
        for i, rep in enumerate(reps, 1):
            b = bottom_rows(rep)
            f = flexed_rows(rep)
            bL, bR = med([r["vL"] for r in b]), med([r["vR"] for r in b])
            pL = max([r["vL"] for r in f if np.isfinite(r["vL"])], default=np.nan)
            pR = max([r["vR"] for r in f if np.isfinite(r["vR"])], default=np.nan)
            rp = rep["report"] or {}
            out(f"   {i:3d} {fmt(bL, 3, 7)} {fmt(bR, 3, 7)} "
                f"{fmt(bL - offL, 3, 7)} {fmt(bR - offR, 3, 7)} "
                f"{fmt(pL, 3, 7)} {fmt(pR, 3, 7)} "
                f"{fmt(rp.get('valgus_s'), 2, 7)}")
            by_cond.setdefault(info["stance"], []).append((bL, bR))
        out("")

    out("-" * 78)
    out("CONDITION MEANS (bottom-window median, neutral-referenced)")
    out("-" * 78)
    out(f"{'condition':10s} {'reps':>5s} {'refL':>8s} {'refR':>8s} {'mean':>8s} {'|L-R|':>8s}")
    summary = {}
    for cond in ("NORMAL", "OUT", "IN"):
        vals = by_cond.get(cond, [])
        if not vals:
            continue
        L = med([v[0] for v in vals]) - offL
        R = med([v[1] for v in vals]) - offR
        summary[cond] = (L, R)
        out(f"{cond:10s} {len(vals):5d} {fmt(L, 3, 8)} {fmt(R, 3, 8)} "
            f"{fmt((L + R) / 2, 3, 8)} {fmt(abs(L - R), 3, 8)}")
    out("")

    out("-" * 78)
    out("THE VERDICT, FROM THE ENGINE'S OWN PER-REP FLAGS")
    out("-" * 78)
    out("Scored on exactly what the athlete was shown: RepReport.valgus - ONE signal,")
    out(f"i.e. the knees closing {RE.VALGUS_SEP_DROP_MM} mm inside her standing knee gap, held for "
        f"{RE.VALGUS_FAULT_FRACTION:.0%} of the rep,")
    out("anywhere in descent, bottom or ascent. The distributions above are for FITTING")
    out("the threshold; this section judges the detector as it actually ships.")
    out("")
    tally = {}
    for info, reps in sets:
        c = info["stance"]
        hit, tot, frac = tally.get(c, (0, 0, []))
        for rep in reps:
            r = rep["report"]
            tot += 1
            if r.get("valgus"):
                hit += 1
            f = [x for x in (r.get("valgus_frac"),)
                 if x is not None and np.isfinite(x)]
            frac.append(max(f) if f else 0.0)
        tally[c] = (hit, tot, frac)

    out(f"{'condition':10s} {'reps':>5s} {'flagged':>9s} {'rate':>7s} {'mean hold':>10s}")
    for c in ("IN", "NORMAL", "OUT"):
        if c not in tally:
            continue
        hit, tot, frac = tally[c]
        out(f"{c:10s} {tot:5d} {hit:9d} {hit / tot:7.0%} {np.mean(frac):9.0%}")
    out("")

    ok = True
    if "IN" in tally:
        hit, tot, _ = tally["IN"]
        good = hit > 0
        ok &= good
        out(f"SENSITIVITY  {hit}/{tot} knees-in reps flagged   "
            f"{'PASS' if good else 'FAIL'}  (a detector must fire on the fault)")
    else:
        ok = False
        out("SENSITIVITY  no knees-in set in this session   CANNOT EVALUATE")
    if "NORMAL" in tally:
        hit, tot, _ = tally["NORMAL"]
        good = hit / tot <= 0.10
        ok &= good
        out(f"FALSE ALARM  {hit}/{tot} normal reps flagged ({hit / tot:.0%})   "
            f"{'PASS' if good else 'FAIL'}  (want <= 10%)")
    if "OUT" in tally:
        hit, tot, _ = tally["OUT"]
        good = hit == 0
        ok &= good
        out(f"ADVERSARIAL  {hit}/{tot} knees-OUT reps flagged   "
            f"{'PASS' if good else 'FAIL'}  (must never fire)")
    out("")
    out(f"VERDICT: {'valgus is USABLE as a fault detector' if ok else 'valgus FAILS -- do not present it as a fault detector'}")
    out("One subject, one rig. This is an operating point, not a validated threshold.")
    out("")
    return summary


def section_valgus_threshold(sets, offL, offR, out):
    out("=" * 78)
    out("4.  VALGUS_SEP_DROP_MM SWEEP")
    out("=" * 78)
    out("Per-rep classification if the threshold were applied to the neutral-referenced")
    out("bottom-window median. A usable threshold flags the knees-in reps and leaves the")
    out("normal and knees-out reps alone.")
    out("")
    reps_by_cond = {}
    for info, reps in sets:
        for rep in reps:
            b = bottom_rows(rep)
            bL = med([r["vL"] for r in b]) - offL
            bR = med([r["vR"] for r in b]) - offR
            worst = np.nanmax([bL, bR]) if (np.isfinite(bL) or np.isfinite(bR)) else np.nan
            reps_by_cond.setdefault(info["stance"], []).append(worst)

    out(f"{'thresh':>7s} {'IN flagged':>12s} {'NORMAL flagged':>15s} {'OUT flagged':>12s}")
    best, best_score = None, -1
    for thr in np.arange(0.01, 0.161, 0.01):
        row = {}
        for cond in ("IN", "NORMAL", "OUT"):
            v = [x for x in reps_by_cond.get(cond, []) if np.isfinite(x)]
            row[cond] = (sum(1 for x in v if x > thr), len(v))
        score = (row["IN"][0] / max(row["IN"][1], 1)
                 - row["NORMAL"][0] / max(row["NORMAL"][1], 1)
                 - row["OUT"][0] / max(row["OUT"][1], 1))
        if score > best_score:
            best, best_score = thr, score
        cell = lambda c: "{}/{}".format(*row[c])
        out(f"{thr:7.2f} {cell('IN'):>12s} {cell('NORMAL'):>15s} {cell('OUT'):>12s}")
    out("")
    out(f"current VALGUS_SEP_DROP_MM = {RE.VALGUS_SEP_DROP_MM} mm")
    out(f"best separation at      = {best:.2f}  (score {best_score:+.2f}, 1.0 = perfect)")
    out("NOTE: this is a threshold fitted to ONE session by one subject. It is a")
    out("      starting value for the testing week, not a validated detection threshold.")
    out("")


def section_depth(sets, out):
    out("=" * 78)
    out("5.  DEPTH  (DEPTH_OFFSET / PARALLEL_BAND)")
    out("=" * 78)
    out("Bottom-window median depth_margin per rep, against the label the set was")
    out("captured under.")
    out("")
    out(f"{'set':34s} {'label':9s} {'reps':>5s} {'margin_mm':>10s} {'sd':>6s} "
        f"{'range':>15s}")
    groups = {}
    for info, reps in sets:
        vals = []
        for rep in reps:
            b = bottom_rows(rep)
            vals.append(med([r["depth"] for r in b]))
        vals = [v for v in vals if np.isfinite(v)]
        if not vals:
            continue
        groups.setdefault(info["depth_label"], []).extend(vals)
        out(f"{info['label'][:34]:34s} {info['depth_label']:9s} {len(vals):5d} "
            f"{np.median(vals):10.1f} {np.std(vals):6.1f} "
            f"{f'{min(vals):.0f}..{max(vals):.0f}':>15s}")
    out("")
    out("-" * 78)
    out("CLASS SEPARATION")
    out("-" * 78)
    for name in ("partial", "parallel", "deep"):
        v = groups.get(name, [])
        if v:
            out(f"{name:9s} n={len(v):2d}  median {np.median(v):7.1f} mm   "
                f"range {min(v):.0f}..{max(v):.0f}")
    out("")
    cur_lo = RE.DEPTH_OFFSET - RE.PARALLEL_BAND
    cur_hi = RE.DEPTH_OFFSET + RE.PARALLEL_BAND
    out(f"current: deep < {cur_lo:.0f} <= parallel <= {cur_hi:.0f} < partial"
        f"   (DEPTH_OFFSET={RE.DEPTH_OFFSET:.0f}, PARALLEL_BAND={RE.PARALLEL_BAND:.0f})")
    out("")
    out(f"{'set':34s} {'label':9s} {'classified as':>28s}")
    wrong = 0
    for info, reps in sets:
        got = {}
        for rep in reps:
            b = bottom_rows(rep)
            m = med([r["depth"] for r in b])
            c = RE.classify_depth(m)
            got[c] = got.get(c, 0) + 1
            if c != info["depth_label"]:
                wrong += 1
        out(f"{info['label'][:34]:34s} {info['depth_label']:9s} "
            f"{', '.join(f'{k} x{v}' for k, v in sorted(got.items())):>28s}")
    out("")
    out(f"misclassified reps: {wrong}")

    if groups.get("parallel"):
        par = groups["parallel"]
        fitted = float(np.median(par))
        out("")
        out(f"FITTED DEPTH_OFFSET = {fitted:.0f} mm  (median of the reps she called parallel; "
            f"current {RE.DEPTH_OFFSET:.0f})")
        d, p = groups.get("deep", []), groups.get("partial", [])
        if d and p:
            lo_gap = min(par) - max(d)
            hi_gap = min(p) - max(par)
            out(f"gap parallel..deep    = {lo_gap:+.0f} mm")
            out(f"gap partial..parallel = {hi_gap:+.0f} mm")
            half = min(abs(lo_gap), abs(hi_gap)) / 2 + 0.0
            out(f"widest band that still separates the three classes: +/-{half:.0f} mm "
                f"(current {RE.PARALLEL_BAND:.0f})")
            if lo_gap < 0 or hi_gap < 0:
                out("!! classes OVERLAP -- no band separates them; depth labels and the")
                out("   measure disagree, which needs resolving before the testing week.")
    out("")


def section_descriptive(sets, out):
    out("=" * 78)
    out("6.  DESCRIPTIVE TRACES  (symmetry, shoulder tilt -- no longer scored faults)")
    out("=" * 78)
    out("The 27 Aug rewrite removed knee_asym and shoulder_tilt as penalised faults;")
    out("they are traces now. These ranges are what the post-rep screen must plot.")
    out("")
    out(f"{'set':34s} {'sym_mean':>9s} {'sym_p90':>8s} {'tilt_med':>9s} {'|tilt|_p90':>11s}")
    for info, reps in sets:
        syms, tilts = [], []
        for rep in reps:
            f = flexed_rows(rep)
            syms += [r["sym"] for r in f if np.isfinite(r["sym"])]
            tilts += [r["tilt"] for r in f if np.isfinite(r["tilt"])]
        if not syms:
            continue
        out(f"{info['label'][:34]:34s} {np.mean(syms):9.1f} "
            f"{np.percentile(syms, 90):8.1f} {np.median(tilts):9.1f} "
            f"{np.percentile(np.abs(tilts), 90):11.1f}")
    out("")
    out("The deliberate shoulder-tilt set should stand clear of the others on the last")
    out("two columns. If it does not, the tilt trace is not showing what it claims to.")
    out("")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("session", help="recordings/<session_id> directory")
    ap.add_argument("--out", default=None, help="also write the report to this file")
    ap.add_argument("--channel", default="euro",
                    choices=["stored", "raw", "euro", "kalman"],
                    help="3D stream to analyse; 'euro' is the current filter, 'stored' is the stream as recorded")
    ap.add_argument("--euro-min-cutoff", type=float, default=1.0)
    ap.add_argument("--euro-beta", type=float, default=0.020)
    a = ap.parse_args()

    paths = [p for p in sorted(glob.glob(os.path.join(a.session, "*.npz")))
             if not p.endswith("_frametimes.npz")]
    if not paths:
        raise SystemExit(f"no .npz sets in {a.session}")

    lines = []

    def out(s=""):
        print(s)
        lines.append(s)

    sets = [replay(p, a.channel, a.euro_min_cutoff, a.euro_beta)
            for p in paths]

    out("#" * 78)
    out(f"# THRESHOLD ANALYSIS -- {a.session}")
    out(f"# channel: {a.channel}"
        + (f"  (One Euro {a.euro_min_cutoff} / {a.euro_beta})"
           if a.channel == "euro" else ""))
    out(f"# engine: VALGUS_SEP_DROP_MM={RE.VALGUS_SEP_DROP_MM}  "
        f"VALGUS_FAULT_FRACTION={RE.VALGUS_FAULT_FRACTION}  "
        f"DEPTH_OFFSET={RE.DEPTH_OFFSET}  PARALLEL_BAND={RE.PARALLEL_BAND}")
    out("#" * 78)
    out("")

    section_overview(sets, out)
    offL, offR = section_standing(sets, out)
    section_valgus(sets, offL, offR, out)
    section_valgus_threshold(sets, offL, offR, out)
    section_depth(sets, out)
    section_descriptive(sets, out)

    if a.out:
        os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
        with open(a.out, "w") as fh:
            fh.write("\n".join(lines) + "\n")
        print(f"\nwritten to {a.out}")


if __name__ == "__main__":
    main()
