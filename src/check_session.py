"""Verify a recorded session the same day, while the rig is still standing."""
from __future__ import annotations
import argparse
import glob
import hashlib
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from session_io import load_session_arrays

try:
    import cv2
except Exception:
    cv2 = None


def set_files(d):
    return sorted(p for p in glob.glob(os.path.join(d, "*.npz"))
                  if not p.endswith("_frametimes.npz"))


def moving_median(x, w):
    """(T,) -> (T,) centred moving median, edges clamped."""
    w = max(3, int(w) | 1)
    h, T = w // 2, len(x)
    out = np.empty(T)
    for i in range(T):
        seg = x[max(0, i - h):min(T, i + h + 1)]
        seg = seg[np.isfinite(seg)]
        out[i] = np.median(seg) if seg.size else np.nan
    return out


def hf_noise_mm(kp, fps):
    """Per-joint high-frequency scatter: sd of the residual about a ~1 s moving median, so slow real movement is removed and measurement noise is left."""
    T, J, _ = kp.shape
    w = max(3, int(round(fps)))
    out = np.full(J, np.nan)
    for j in range(J):
        res = []
        for ax in range(3):
            v = kp[:, j, ax]
            if np.isfinite(v).sum() < max(10, w):
                res = []
                break
            res.append(v - moving_median(v, w))
        if res:
            r = np.stack(res, 1)
            r = r[np.all(np.isfinite(r), 1)]
            if len(r) > 10:
                out[j] = float(np.sqrt(np.mean(np.sum(r ** 2, 1))))
    return out


def video_report(path_stem, cams, n3d):
    """-> (list of per-camera strings, ok flag)."""
    lines, ok = [], True
    for c in cams:
        p = f"{path_stem}_cam{c}.avi"
        if not os.path.exists(p):
            lines.append(f"cam{c}: MISSING"); ok = False
            continue
        mb = os.path.getsize(p) / 1e6
        n = None
        if cv2 is not None:
            cap = cv2.VideoCapture(p)
            n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            cap.release()
        tail = ""
        if n is not None:
            frac = n / n3d if n3d else 0.0
            tail = f", {n} frames ({100 * frac:.0f}% of 3D)"
            if frac < 0.9:
                ok = False
                tail += "  << FRAMES LOST"
        lines.append(f"cam{c}: {mb:6.1f} MB{tail}")
    ft = f"{path_stem}_frametimes.npz"
    if os.path.exists(ft):
        z = np.load(ft)
        lines.append("frametimes: " + ", ".join(f"{k}={len(z[k])}" for k in z.files))
    else:
        lines.append("frametimes: MISSING"); ok = False
    return lines, ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("session")
    ap.add_argument("--manifest", action="store_true",
                    help="also write MANIFEST.sha256 for verifying a backup copy")
    a = ap.parse_args()
    d = a.session.rstrip("/")
    files = set_files(d)
    if not files:
        sys.exit(f"no set .npz files in {d}")

    print(f"\nSESSION {os.path.basename(d)}   {len(files)} sets\n" + "=" * 78)
    fps_all, prints, problems, statics = {}, [], [], []
    for p in files:
        A = load_session_arrays(p)
        kp, raw, t, meta = A["kp"], A["kp_raw"], A["t"], A["meta"]
        T = len(t)
        dur = float(t[-1] - t[0]) if T > 1 else 0.0
        fps = (T - 1) / dur if dur > 0 else 0.0
        fps_all[os.path.basename(p)] = fps
        b = np.all(~np.isfinite(kp), axis=(1, 2))
        lead = int(np.argmax(~b)) if b.any() and not b.all() else (T if b.all() else 0)
        tail = int(np.argmax(~b[::-1])) if b.any() and not b.all() else 0
        inner = b[lead:T - tail] if T - tail > lead else np.zeros(0, bool)
        blank = float(inner.mean()) if inner.size else 0.0
        holes = float(np.mean(~np.isfinite(kp[lead:T - tail, :, 0]))) if inner.size else 0.0
        chans = [n for n in ("kp", "kp_raw", "pts2d", "conf") if A[n] is not None]
        name = os.path.basename(p)[:-4]

        print(f"\n{name}")
        print(f"  label={meta.get('label','?')!r}  target={meta.get('target','?')}  "
              f"reps_detected={meta.get('reps_detected','?')}")
        drv = meta.get("driven_by")
        ssi = meta.get("set_start_index")
        pre = (t[ssi] - t[0]) if (ssi and 0 < ssi < len(t)) else 0.0
        if drv == "unity":
            flag = "" if pre >= 10.0 else "   SHORT PRE-ROLL - replay may mis-baseline"
            print(f"  driven_by=unity (live path)   pre-roll {pre:.1f} s "
                  f"before the set{flag}")
        elif drv == "terminal":
            print("  driven_by=terminal - the terminal gate ran, NOT Unity's. "
                  "This set is not\n     evidence about the live path; reconnect "
                  "Unity and re-shoot if it matters.")
        else:
            print("  driven_by absent - recorded before 11 Sep, so the terminal "
                  "gate ran.")
        print(f"  {T} frames, {dur:.1f} s, {fps:.1f} fps  |  walk-in {lead} fr, "
              f"walk-out {tail} fr (trim these)")
        print(f"  INSIDE the set: no-skeleton frames {100*blank:.1f}%, "
              f"missing joints {100*holes:.1f}%")
        print(f"  channels: {', '.join(chans)}")
        if raw is None:
            problems.append(f"{name}: NO RAW CHANNEL -- Kalman cannot be re-tuned from this set")
        else:
            both = np.all(np.isfinite(kp), 2) & np.all(np.isfinite(raw), 2)
            if both.any():
                dmm = np.linalg.norm(kp - raw, axis=2)[both]
                print(f"  filter moves points  median {np.median(dmm):5.1f} mm, "
                      f"p90 {np.percentile(dmm, 90):5.1f} mm, max {dmm.max():5.1f} mm")
        vs = meta.get("video")
        if vs:
            print(f"  video: {vs.get('written','?')} frames/cam written, "
                  f"{vs.get('dropped','?')} dropped")
            if vs.get("dropped"):
                problems.append(f"{name}: {vs['dropped']} video frames dropped")
        lines, ok = video_report(p[:-4], meta.get("cameras", [0, 1, 2]), T)
        for ln in lines:
            print(f"    {ln}")
        if not ok:
            problems.append(f"{name}: video incomplete (see above)")
        if blank > 0.02:
            problems.append(f"{name}: {100*blank:.1f}% of IN-SET frames have no skeleton "
                            f"(lead-in/tail are excluded, so this is real tracking loss)")
        prints.append((name, meta.get("calibration")))
        if "static" in meta.get("label", "").lower() and raw is not None:
            statics.append((name, raw, kp, fps))

    print("\n" + "=" * 78)
    fps_bad = [k for k, v in fps_all.items() if v < 7.0]
    print(f"capture rate: {min(fps_all.values()):.1f}-{max(fps_all.values()):.1f} fps"
          + ("  << SLOW SETS: " + ", ".join(fps_bad) if fps_bad else ""))
    fp = {str(c): n for n, c in prints}
    if len({str(c) for _, c in prints}) == 1:
        c = prints[0][1] or {}
        print(f"calibration: ONE for the whole session  "
              f"extrinsics={c.get('extrinsics.json', '?')}  "
              f"vertical={c.get('vertical.json', '?')}")
    else:
        print("!! calibration CHANGED mid-session -- sets are not directly comparable:")
        for n, c in prints:
            print(f"     {n}: {c}")
        problems.append("calibration is not constant across the session")

    for name, raw, kp, fps in statics:
        nr, ns = hf_noise_mm(raw, fps), hf_noise_mm(kp, fps)
        print(f"\nNOISE FLOOR from {name} (sd about a 1 s moving median):")
        print(f"  RAW      median joint {np.nanmedian(nr):5.1f} mm   "
              f"worst {np.nanmax(nr):5.1f} mm")
        print(f"  FILTERED median joint {np.nanmedian(ns):5.1f} mm   "
              f"worst {np.nanmax(ns):5.1f} mm")
        print(f"  => measurement_var should be about "
              f"{np.nanmedian(nr) ** 2:.0f} mm^2 (currently 4.0, i.e. a claim of "
              f"{2.0:.1f} mm keypoint accuracy)")

    print("\n" + "=" * 78)
    if problems:
        print("PROBLEMS:")
        for x in problems:
            print("  !! " + x)
    else:
        print("No problems found. Back it up now -- two copies, one off this machine.")

    if a.manifest:
        out = os.path.join(d, "MANIFEST.sha256")
        names = sorted(f for f in os.listdir(d) if f != "MANIFEST.sha256")
        with open(out, "w") as fh:
            for f in names:
                h = hashlib.sha256()
                with open(os.path.join(d, f), "rb") as g:
                    for chunk in iter(lambda: g.read(1 << 20), b""):
                        h.update(chunk)
                fh.write(f"{h.hexdigest()}  {f}\n")
        print(f"\nwrote {out} ({len(names)} files)")
        print("verify a copy with:  cd <copy> && shasum -c MANIFEST.sha256")


if __name__ == "__main__":
    main()
