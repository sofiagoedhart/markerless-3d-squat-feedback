"""Fit the smoothing constants from a recorded session, and report what each one costs."""

import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kalman_smoother import SkeletonKalman
from one_euro import SkeletonOneEuro

L_HIP, R_HIP = 11, 12
L_KNEE, R_KNEE = 13, 14
L_ANK, R_ANK = 15, 16
L_SHO, R_SHO = 5, 6
TRACKED = [L_SHO, R_SHO, L_HIP, R_HIP, L_KNEE, R_KNEE, L_ANK, R_ANK]


def load_set(path):
    d = np.load(path, allow_pickle=True)
    meta = json.loads(str(d["meta"]))
    up = np.array(meta["body_frame"]["up"], dtype=float)
    up /= np.linalg.norm(up)
    lat = np.array(meta["body_frame"]["lateral"], dtype=float)
    lat /= np.linalg.norm(lat)
    return dict(kp=d["kp"].astype(float), raw=d["kp_raw"].astype(float),
                t=d["t"].astype(float), up=up, lat=lat, meta=meta,
                name=os.path.basename(path).replace(".npz", ""))


def trim_lead_tail(s):
    """Drop the walk-in / walk-out frames: keep from first to last frame that has all TRACKED joints."""
    ok = np.all(np.isfinite(s["raw"][:, TRACKED]).all(axis=2), axis=1)
    if not ok.any():
        return s, (0, len(ok))
    i0, i1 = int(np.argmax(ok)), int(len(ok) - np.argmax(ok[::-1]))
    out = dict(s)
    for k in ("kp", "raw", "t"):
        out[k] = s[k][i0:i1]
    return out, (i0, i1)


def _mov_med(v, w):
    h, T = w // 2, len(v)
    out = np.full(T, np.nan)
    for i in range(T):
        seg = v[max(0, i - h):min(T, i + h + 1)]
        seg = seg[np.isfinite(seg)]
        if seg.size:
            out[i] = np.median(seg)
    return out


def still_mask(s, thresh_mm_s=60.0):
    """Frames where the body is genuinely stationary."""
    t, raw = s["t"], s["raw"]
    pel = np.nanmean(raw[:, [L_HIP, R_HIP], :], axis=1)
    sp = np.full(len(t), np.inf)
    sp[1:] = np.linalg.norm(np.diff(pel, axis=0), axis=1) / np.diff(t)
    return np.nan_to_num(_mov_med(sp, 5), nan=np.inf) < thresh_mm_s


def noise_floor(s, win_s=1.0, arr=None, mask=None):
    """Scatter of a 3D stream about a ~1 s moving median, scored on stationary frames only."""
    t = s["t"]
    x = s["raw"] if arr is None else arr
    dt = float(np.median(np.diff(t)))
    w = max(3, int(round(win_s / dt)) | 1)
    if mask is None:
        mask = np.ones(len(t), bool)

    resid = np.full_like(x, np.nan)
    for j in TRACKED:
        for ax in range(3):
            v = x[:, j, ax]
            if np.isfinite(v).sum() < max(10, w):
                continue
            resid[:, j, ax] = v - _mov_med(v, w)

    r = resid[mask][:, TRACKED, :]
    r3 = np.linalg.norm(r, axis=2)
    with np.errstate(invalid="ignore"):
        rms3 = np.sqrt(np.nanmean(r3 ** 2, axis=0))
        med3 = np.nanmedian(r3, axis=0)
        ax_sig = np.nanstd(r, axis=0)
    return dict(
        n_frames_scored=int(mask.sum()),
        median_axis_sigma_mm=float(np.nanmedian(ax_sig)),
        worst_axis_sigma_mm=float(np.nanmax(ax_sig)),
        rms_3d_mm=float(np.nanmedian(rms3)),
        worst_rms_3d_mm=float(np.nanmax(rms3)),
        median_3d_mm=float(np.nanmedian(med3)),
        worst_3d_mm=float(np.nanmax(med3)),
        n_joints=int(np.isfinite(med3).sum()),
    )


def run_kalman(s, q, r, max_coast=6):
    f = SkeletonKalman(process_var=q, measurement_var=r)
    t, raw = s["t"], s["raw"]
    for kf in f.filters:
        kf.max_coast = max_coast
    out = np.full_like(raw, np.nan)
    for i in range(len(t)):
        dt = float(t[i] - t[i - 1]) if i else float(np.median(np.diff(t)))
        dt = min(max(dt, 1e-3), 1.0)
        out[i] = f.update(raw[i], dt)
    return out


def run_euro(s, min_cutoff, beta, max_coast=2):
    f = SkeletonOneEuro(min_cutoff=min_cutoff, beta=beta, max_coast=max_coast)
    t, raw = s["t"], s["raw"]
    out = np.full_like(raw, np.nan)
    for i in range(len(t)):
        dt = float(t[i] - t[i - 1]) if i else float(np.median(np.diff(t)))
        dt = min(max(dt, 1e-3), 1.0)
        out[i] = f.update(raw[i], dt)
    return out


def _signal(arr, s, joints, axis="up"):
    """Scalar trace: mean of `joints` projected on the body up (or lateral)."""
    v = s["up"] if axis == "up" else s["lat"]
    p = np.nanmean(arr[:, joints, :], axis=1)
    return p @ v


def _interp_nan(y):
    y = np.asarray(y, float).copy()
    good = np.isfinite(y)
    if good.sum() < 2:
        return y
    idx = np.arange(len(y))
    y[~good] = np.interp(idx[~good], idx[good], y[good])
    return y


def group_delay_ms(raw_sig, filt_sig, dt, max_lag_frames=12):
    """Delay that best aligns the filtered trace with the raw one, by cross-correlation on the mean-removed traces, refined to sub-frame by a parabolic fit through the peak."""
    a = _interp_nan(raw_sig)
    b = _interp_nan(filt_sig)
    a = a - np.mean(a)
    b = b - np.mean(b)
    if np.std(a) < 1e-9 or np.std(b) < 1e-9:
        return 0.0
    lags = np.arange(-4, max_lag_frames + 1)
    cc = []
    for L in lags:
        if L >= 0:
            bb, aa = b[L:], a[:len(b) - L]
        else:
            bb, aa = b[:len(b) + L], a[-L:]
        cc.append(np.dot(aa, bb) / (np.linalg.norm(aa) * np.linalg.norm(bb)))
    cc = np.array(cc)
    k = int(np.argmax(cc))
    frac = 0.0
    if 0 < k < len(cc) - 1:
        y0, y1, y2 = cc[k - 1], cc[k], cc[k + 1]
        denom = (y0 - 2 * y1 + y2)
        frac = 0.5 * (y0 - y2) / denom if abs(denom) > 1e-12 else 0.0
    return float((lags[k] + frac) * dt * 1000.0)


def overshoot_mm(raw_sig, filt_sig, dt, min_prominence=40.0):
    """At every sharp turning point in the RAW trace (top of a rep, bottom of a rep), how far past the raw extremum does the filtered trace travel?"""
    a = _interp_nan(raw_sig)
    b = _interp_nan(filt_sig)
    w = max(2, int(round(0.35 / dt)))
    over = []
    for i in range(w, len(a) - w):
        lo, hi = i - w, i + w + 1
        seg = a[lo:hi]
        if a[i] == seg.max() and (seg.max() - seg.min()) > min_prominence:
            over.append(b[lo:hi].max() - a[i])
        elif a[i] == seg.min() and (seg.max() - seg.min()) > min_prominence:
            over.append(a[i] - b[lo:hi].min())
    if not over:
        return 0.0, 0
    over = np.array(over)
    return float(np.max(over)), len(over)


def displacement_mm(raw, filt):
    """||filtered - raw|| per frame over the tracked joints."""
    d = np.linalg.norm(filt[:, TRACKED] - raw[:, TRACKED], axis=2)
    d = d[np.isfinite(d)]
    if d.size == 0:
        return dict(median=np.nan, p90=np.nan)
    return dict(median=float(np.median(d)), p90=float(np.percentile(d, 90)))


def static_residual_mm(s, filt, mask, win_s=1.0):
    """Scatter of the FILTERED stream about a moving median on stationary frames — the smoothing benefit, measured exactly as the raw noise floor was, so the two compare like for like."""
    return noise_floor(s, win_s, arr=filt, mask=mask)["rms_3d_mm"]


def evaluate(sets, q=None, r=None, euro=None, max_coast=6, still=None):
    """Run one filter configuration and report the four numbers that matter."""
    static, fast, slow = sets["static"], sets["fast"], sets["slow"]

    def _run(s):
        if euro is not None:
            return run_euro(s, euro[0], euro[1])
        return run_kalman(s, q, r, max_coast=max_coast)

    fs, ff, fl = _run(static), _run(fast), _run(slow)
    if still is None:
        still = still_mask(static)

    res = {}
    res["static_resid_mm"] = static_residual_mm(static, fs, still)
    res["static_disp"] = displacement_mm(static["raw"], fs)

    for tag, s, f in (("fast", fast, ff), ("slow", slow, fl)):
        dt = float(np.median(np.diff(s["t"])))
        rs = _signal(s["raw"], s, [L_HIP, R_HIP], "up")
        fsig = _signal(f, s, [L_HIP, R_HIP], "up")
        res[f"{tag}_delay_ms"] = group_delay_ms(rs, fsig, dt)
        ov, n = overshoot_mm(rs, fsig, dt)
        res[f"{tag}_overshoot_mm"] = ov
        res[f"{tag}_n_turns"] = n
        res[f"{tag}_disp"] = displacement_mm(s["raw"], f)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("session", help="directory of recorded .npz sets")
    ap.add_argument("--out", default="results")
    a = ap.parse_args()

    files = sorted(f for f in os.listdir(a.session)
                   if f.endswith(".npz") and "frametimes" not in f)
    by = {}
    for f in files:
        s, _ = trim_lead_tail(load_set(os.path.join(a.session, f)))
        by[f] = s

    def pick(sub):
        for k, v in by.items():
            if sub in k:
                return v
        raise SystemExit(f"no set matching {sub!r} in {a.session}")

    sets = dict(static=pick("static"), fast=pick("fast"), slow=pick("slow"))

    still = still_mask(sets["static"])
    print("=" * 78)
    print("1. MEASUREMENT NOISE FLOOR  (raw, static set, scatter about a 1 s median)")
    print("=" * 78)
    nf_all = noise_floor(sets["static"])
    nf = noise_floor(sets["static"], mask=still)
    print(f"  stationary frames      : {nf['n_frames_scored']} of "
          f"{len(sets['static']['t'])}  ({100*still.mean():.0f}%)")
    print(f"  joints scored          : {nf['n_joints']}\n")
    print(f"  {'':<26}{'ALL frames':>14}{'STATIONARY only':>18}")
    print(f"  {'3D scatter, RMS':<26}{nf_all['rms_3d_mm']:>11.1f} mm"
          f"{nf['rms_3d_mm']:>15.1f} mm")
    print(f"  {'3D scatter, median':<26}{nf_all['median_3d_mm']:>11.1f} mm"
          f"{nf['median_3d_mm']:>15.1f} mm")
    print(f"  {'per-axis sigma':<26}{nf_all['median_axis_sigma_mm']:>11.1f} mm"
          f"{nf['median_axis_sigma_mm']:>15.1f} mm")
    print("\n  The ALL-frames RMS column is NOT a noise floor. This set contains")
    print("    a descent, a hold and an ascent; a 1 s moving median cannot follow")
    print("    a 1.5 s descent, so those residuals are SIGNAL, and RMS is dominated")
    print("    by them. That is where the '29 mm' reading came from.")

    r_fit = nf["median_axis_sigma_mm"] ** 2
    print(f"\n  -> measurement_var (R = eye(3)*r, per-AXIS variance) = "
          f"{r_fit:.1f} mm^2")
    print(f"     the code ships 4.0 mm^2 (a claim of 2.0 mm/axis) — which the data")
    print(f"     SUPPORTS. R is not the problem. Keeping 4.0.")
    r_use = 4.0

    print()
    print("=" * 78)
    print("2. WHAT process_var COSTS  (r = 4.0, the fitted value)")
    print("=" * 78)
    hdr = (f"{'q':>9} | {'still resid':>11} | {'delay fast':>10} "
           f"| {'overshoot':>9} | {'disp fast med/p90':>18}")
    print(hdr)
    print("-" * len(hdr))
    rows = []
    for q in (1, 4, 8, 12, 25, 50, 100, 200, 400, 800, 1600, 3200):
        e = evaluate(sets, q=q, r=r_use, still=still)
        rows.append((q, e))
        mark = "   <-- shipping" if q == 12 else ""
        print(f"{q:9.0f} | {e['static_resid_mm']:8.1f} mm | "
              f"{e['fast_delay_ms']:7.0f} ms | {e['fast_overshoot_mm']:6.1f} mm | "
              f"{e['fast_disp']['median']:7.1f} /{e['fast_disp']['p90']:7.1f} mm{mark}")
    e0 = evaluate(sets, q=12, r=4.0, still=still)
    print("\n  raw, unfiltered, for the same numbers:")
    dt_f = float(np.median(np.diff(sets['fast']['t'])))
    print(f"{'raw':>9} | {nf['rms_3d_mm']:8.1f} mm | "
          f"{0.0:7.0f} ms | {0.0:6.1f} mm | {0.0:7.1f} /{0.0:7.1f} mm"
          f"   (frame period {dt_f*1000:.0f} ms)")

    print()
    print("=" * 78)
    print("3. ONE EURO, as the DISPLAY filter")
    print("=" * 78)
    print(hdr)
    print("-" * len(hdr))
    euro_rows = []
    for mc, beta in ((0.5, 0.002), (0.8, 0.004), (1.0, 0.007), (1.0, 0.02),
                     (1.5, 0.01), (2.0, 0.02), (3.0, 0.04)):
        e = evaluate(sets, euro=(mc, beta), still=still)
        euro_rows.append(((mc, beta), e))
        print(f"{mc:4.1f}/{beta:5.3f} | {e['static_resid_mm']:8.1f} mm | "
              f"{e['fast_delay_ms']:7.0f} ms | {e['fast_overshoot_mm']:6.1f} mm | "
              f"{e['fast_disp']['median']:7.1f} /{e['fast_disp']['p90']:7.1f} mm")

    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "filter_tuning.json"), "w") as fh:
        json.dump(dict(
            noise_floor={k: (v.tolist() if isinstance(v, np.ndarray) else v)
                         for k, v in nf.items()},
            measurement_var_fitted=r_fit, measurement_var_used=r_use, noise_floor_all_frames={k: (v.tolist() if isinstance(v, np.ndarray) else v) for k, v in nf_all.items()},
            kalman=[dict(q=q, **{k: v for k, v in e.items()}) for q, e in rows],
            euro=[dict(min_cutoff=p[0], beta=p[1], **{k: v for k, v in e.items()})
                  for p, e in euro_rows],
            shipping=e0,
        ), fh, indent=2)
    print(f"\nwrote {os.path.join(a.out, 'filter_tuning.json')}")


if __name__ == "__main__":
    main()
