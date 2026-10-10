#!/usr/bin/env python3
"""Render a session's set dumps as one self-contained HTML report in the review-screen card layout."""
from __future__ import annotations

import argparse
import datetime
import glob
import html
import json
import math
import os
import subprocess
import sys

import report_copy as T

TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "report_template.html")


def load_session(dirpath):
    """Every set record in a dump folder, in the order the sets were performed."""
    out = []
    for path in sorted(glob.glob(os.path.join(dirpath, "*.json"))):
        if os.path.basename(path) == "report.json":
            continue
        try:
            with open(path) as fh:
                rec = json.load(fh)
        except (OSError, ValueError) as e:
            print(f"[report] skipping {os.path.basename(path)}: {e}", file=sys.stderr)
            continue
        if "reps" in rec:
            rec["_file"] = os.path.basename(path)
            out.append(rec)
    out.sort(key=lambda r: r.get("set_index", 0))
    return out


def group_blocks(records, break_at=()):
    """Split the session into blocks."""
    if any("block" in r for r in records):
        keyed = {}
        for r in records:
            keyed.setdefault(int(r.get("block", 1)), []).append(r)
        return [(k, keyed[k]) for k in sorted(keyed)]
    if break_at:
        cuts, blocks, cur, n = sorted(set(break_at)), [], [], 1
        for r in records:
            if r.get("set_index") in cuts and cur:
                blocks.append((n, cur))
                cur, n = [], n + 1
            cur.append(r)
        if cur:
            blocks.append((n, cur))
        return blocks
    return [(1, records)]


def num(x):
    """A finite float, or None."""
    if x is None:
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def fmt(x, dp=0, dash="--"):
    return dash if x is None else f"{x:.{dp}f}"


def e(s):
    return html.escape(str(s), quote=True)


def depth_band_of(rep, target):
    """The green band for this rep, in millimetres, as (lo, hi)."""
    off = num(rep.get("depth_offset_mm"))
    band = num(rep.get("depth_band_mm"))
    pmax = num(rep.get("depth_partial_max_mm"))
    if off is None or band is None:
        return None, None
    lo, hi = off - band, off + band
    t = (target or rep.get("target_depth") or "parallel")
    if t == "partial":
        return hi, pmax
    if t == "deep":
        return None, lo
    return lo, hi


def depth_state(rep, target):
    """green / amber / red / grey for one rep's depth dot."""
    faults = rep.get("faults") or []
    m = num(rep.get("depth_margin_mm"))
    if m is None or "depth_unmeasured" in faults:
        return "grey"
    if "shallow" in faults:
        return "red"
    lo, hi = depth_band_of(rep, target)
    if hi is not None and m > hi:
        return "red"
    if lo is not None and m < lo:
        return "amber"
    return "green"


def valgus_state(rep):
    """sustained / brief / ok / grey for one rep's knee tracking."""
    dev = num(rep.get("valgus_dev_mm"))
    if bool(rep.get("valgus")) and "valgus" in (rep.get("faults") or []):
        return "sustained"
    lim = num(rep.get("valgus_limit_mm"))
    if dev is not None and lim is not None and dev >= abs(lim):
        return "brief"
    return "ok" if dev is not None or rep.get("valgus_traj") else "grey"


def shoulder_state(rep):
    """inside / outside / grey against the engine's own band."""
    b = rep.get("shoulder_band")
    if num(rep.get("shoulder_tilt_deg")) is None or b in (None, "unmeasured"):
        return "grey"
    return "inside" if b == "even" else "outside"


def rep_view(r, target):
    lo, hi = depth_band_of(r, target)
    tilt = num(r.get("shoulder_tilt_deg"))
    return {
        "rep": r.get("rep"),
        "target": r.get("target_depth") or target,
        "depth": num(r.get("depth_margin_mm")),
        "band": [lo, hi],
        "depth_state": depth_state(r, target),
        "valgus_dev": num(r.get("valgus_dev_mm")),
        "valgus_frac": num(r.get("valgus_frac")),
        "valgus_limit": num(r.get("valgus_limit_mm")),
        "valgus_state": valgus_state(r),
        "sym": num(r.get("sym_signed_deg")),
        "sym_abs": num(r.get("symmetry_deg")),
        "sh": None if tilt is None else -tilt,
        "sh_abs": None if tilt is None else abs(tilt),
        "sh_state": shoulder_state(r),
        "sh_even": num(r.get("shoulder_even_deg")),
        "down": num(r.get("descent_s")),
        "up": num(r.get("ascent_s")),
        "pause": num(r.get("bottom_dwell_s")),
        "faults": r.get("faults") or [],
    }


def set_view(rec, pos, block):
    target = rec.get("target") or "parallel"
    return {
        "idx": rec.get("set_index") or pos + 1,
        "label": rec.get("label"),
        "target": target,
        "block": block,
        "referenced": bool((rec.get("reps") or [{}])[0].get("shoulder_referenced", True)),
        "reps": [rep_view(r, target) for r in rec.get("reps") or []],
    }


def view_model(session_id, records, break_at=()):
    sets = []
    for bno, recs in group_blocks(records, break_at):
        for r in recs:
            sets.append(set_view(r, len(sets), bno))
    first = records[0] if records else {}
    copy = {k: getattr(T, k) for k in dir(T) if k.isupper()}
    return {"session": session_id, "captured": first.get("written_at"),
            "driver": first.get("driver"), "sets": sets, "copy": copy,
            "generated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}


def render(session_id, records, break_at=()):
    with open(TEMPLATE, encoding="utf-8") as fh:
        page = fh.read()
    data = json.dumps(view_model(session_id, records, break_at), ensure_ascii=False, allow_nan=False)
    data = data.replace("</", "<\\/")
    page = page.replace("__TITLE__", html.escape(T.SESSION_TITLE.format(session=session_id)))
    return page.replace("/*__DATA__*/null", data)


def write_report(dirpath, out=None, break_at=()):
    """Render the dump folder and return the path written, or None if empty."""
    records = load_session(dirpath)
    if not records:
        return None
    session_id = (records[0].get("session_id")
                  or os.path.basename(os.path.normpath(dirpath)))
    out = out or os.path.join(dirpath, "report.html")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(render(session_id, records, break_at))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("session_dir", help="results/sets/<session_id>")
    ap.add_argument("--out", help="output path (default <session_dir>/report.html)")
    ap.add_argument("--break-at", default="",
                    help="comma-separated set indices that START a new block, "
                         "e.g. --break-at 3,7 for a session rewound twice")
    ap.add_argument("--open", action="store_true", help="open it when done")
    a = ap.parse_args(argv)
    breaks = [int(x) for x in a.break_at.split(",") if x.strip()]
    path = write_report(a.session_dir, a.out, breaks)
    if path is None:
        print(f"[report] no set dumps in {a.session_dir}", file=sys.stderr)
        return 1
    print(f"[report] file://{os.path.abspath(path)}")
    if a.open:
        subprocess.run(["open", path], check=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
