"""Write a standalone HTML copy of the Unity post-set or post-rep review screen from one saved set file."""
import argparse
import datetime as dt
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "review_template.html")
KEEP = ["rep", "target_depth", "variation", "depth_met", "depth_margin_mm", "knee_at_depth",
        "trunk_tibia_deg", "dominance", "descent_s", "ascent_s", "bottom_dwell_s",
        "valgus_s", "valgus_frac", "t_bottom_s", "t_ascent_s", "valgus_t", "valgus_dev_mm",
        "valgus_limit_mm", "depth_offset_mm", "depth_band_mm", "depth_partial_max_mm",
        "symmetry_deg", "sym_signed_deg", "shoulder_tilt_deg", "shoulder_band",
        "shoulder_even_deg", "depth_traj", "valgus_traj", "sym_signed_traj",
        "shoulder_tilt_traj", "faults", "cues"]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("set_json", help="results/sets/<session>/NN_<label>.json")
    ap.add_argument("--mode", choices=["set", "rep"], default="set")
    ap.add_argument("--rep", type=int, default=1, help="rep number for --mode rep")
    ap.add_argument("--set-no", type=int, help="set number shown in the header (default: the file's set index)")
    ap.add_argument("--no-stamp", action="store_true", help="leave the date and time out of the set header")
    ap.add_argument("--fragment", action="store_true",
                    help="omit the doctype/head wrapper (for publishing as a Claude artifact)")
    ap.add_argument("--out", help="output .html (default results/review_html/<session>_<label>_<mode>.html)")
    a = ap.parse_args()

    d = json.load(open(a.set_json))
    reps = [{k: r.get(k) for k in KEEP} for r in d.get("reps", [])]
    if not reps:
        raise SystemExit("no repetitions in that set file")
    idx = 0
    if a.mode == "rep":
        idx = next((i for i, r in enumerate(reps) if r["rep"] == a.rep), None)
        if idx is None:
            raise SystemExit(f"rep {a.rep} not in that set")
    stamp = ""
    if not a.no_stamp and d.get("written_at"):
        t = dt.datetime.strptime(d["written_at"], "%Y-%m-%d %H:%M:%S")
        stamp = f"{t:%a} {t.day} {t:%b %Y}\n{t:%H:%M}"
    what = "post-set summary" if a.mode == "set" else "post-rep summary"
    data = {
        "mode": a.mode, "rep_index": idx, "reps": reps, "stamp": stamp,
        "set_no": a.set_no or d.get("set_index") or 1,
        "meta": f"Reproduction of the Unity <b>{what}</b>, drawn from the saved set results "
                f"<b>{d.get('label', '')}</b>. Buttons that change the session are inactive.",
    }
    title = "Squat Set Review" if a.mode == "set" else "Squat Rep Review"
    html = open(TEMPLATE).read()
    html = html.replace("__TITLE__", title).replace(
        "__DATA__", json.dumps(data, separators=(",", ":")).replace("</", "<\\/"))
    if not a.fragment:
        html = ('<!doctype html>\n<html lang="en"><head><meta charset="utf-8">\n'
                '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
                + html + "\n</html>\n")
    out = a.out or os.path.join(
        "results", "review_html",
        f"{d.get('session_id', 'session')}_{d.get('label', 'set')}_{a.mode}"
        + (f"{a.rep}" if a.mode == "rep" else "") + ".html")
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    open(out, "w").write(html)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
