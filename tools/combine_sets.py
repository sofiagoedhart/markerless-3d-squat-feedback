"""Merge set files from several capture sessions into one session folder, with review pages and a session report."""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import report_session


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("sets", nargs="+", help="set files in the order they should appear")
    ap.add_argument("--out", required=True, help="output folder, e.g. results/sets/video3")
    ap.add_argument("--session", help="session id to give every set (default: the first set's)")
    ap.add_argument("--rep-page", action="append", default=[], metavar="SET:REP",
                    help="also write a post-rep page, e.g. 3:1 for set 3 rep 1")
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)
    recs = [json.load(open(p)) for p in a.sets]
    sid = a.session or recs[0]["session_id"]
    paths = []
    for i, (src, r) in enumerate(zip(a.sets, recs), 1):
        r["source_file"] = os.path.relpath(src, os.path.dirname(os.path.abspath(a.out)))
        r["source_session_id"], r["source_set_index"] = r["session_id"], r["set_index"]
        r["session_id"], r["set_index"] = sid, i
        r["label"] = r.get("label") or r.get("target")
        p = os.path.join(a.out, f"{i:02d}_{r['label']}.json")
        json.dump(r, open(p, "w"), indent=1)
        paths.append(p)

    combined = {"session_id": sid, "sets": recs}
    json.dump(combined, open(os.path.join(a.out, "session_results.json"), "w"), indent=1)

    exp = [sys.executable, os.path.join(HERE, "export_review_html.py")]
    for p, r in zip(paths, recs):
        subprocess.run(exp + [p, "--mode", "set", "--set-no", str(r["set_index"]),
                              "--out", os.path.join(a.out, f"set{r['set_index']}_{r['label']}_summary.html")],
                       check=True)
    for spec in a.rep_page:
        s, rep = (int(x) for x in spec.split(":"))
        r = recs[s - 1]
        subprocess.run(exp + [paths[s - 1], "--mode", "rep", "--rep", str(rep), "--set-no", str(s),
                              "--out", os.path.join(a.out, f"set{s}_{r['label']}_rep{rep}_summary.html")],
                       check=True)

    report_session.write_report(a.out, os.path.join(a.out, "session_report.html"))
    print("\n".join(sorted(os.listdir(a.out))))


if __name__ == "__main__":
    main()
