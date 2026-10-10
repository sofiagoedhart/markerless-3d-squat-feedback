"""Compare per-repetition depth under different smoothing filters on the same recording."""
import argparse
import glob
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import metrics as M
from session_io import load_session
from replay_to_unity import build, refilter


class A:
    def __init__(self, channel, **kw):
        self.channel = channel
        self.euro_min_cutoff = kw.get("mc", 1.0)
        self.euro_beta = kw.get("beta", 0.020)
        self.process_var = kw.get("q", 12.0)
        self.measurement_var = kw.get("r", 4.0)


def reps_for(path, channel, **kw):
    frames, meta = load_session(path)
    if channel != "stored":
        frames = refilter(path, frames, A(channel, **kw))
    _, eng, _, _, _ = build(frames, meta, target=meta.get("target", "parallel"))
    out = []
    for kp, t in frames:
        st = eng.update(kp, t)
        if st["rep_completed"]:
            r = st["last_rep"]
            out.append((r.get("depth_margin_mm"), r.get("variation"),
                        r.get("faults", [])))
    return out


ap = argparse.ArgumentParser()
ap.add_argument("session", nargs="?", default="recordings/2026-08-30_sets")
a = ap.parse_args()

files = sorted(f for f in glob.glob(os.path.join(a.session, "*.npz"))
               if "frametimes" not in f)

print("depth_margin_mm per rep — hips relative to the knee. LOWER = deeper.")
print("The partial/parallel/deep classification is taken from this by the")
print("engine's target+offset rule, so read the numbers, not the labels.\n")
print(f"{'set':<36}{'channel':<10}{'per-rep depth margin (mm)'}")
print("-" * 100)

agg = {}
for f in files:
    name = os.path.basename(f).replace(".npz", "")[:34]
    for ch in ("stored", "raw", "euro"):
        try:
            r = reps_for(f, ch)
        except SystemExit as e:
            print(f"{name:<36}{ch:<10}{e}")
            continue
        except Exception as e:
            print(f"{name:<36}{ch:<10}!! {type(e).__name__}: {e}")
            continue
        vals = [x[0] for x in r if x[0] is not None]
        if not vals:
            print(f"{name:<36}{ch:<10}(no reps detected)")
            continue
        s = " ".join(f"{v:6.0f}" for v in vals)
        print(f"{name:<36}{ch:<10}{s}")
        agg.setdefault(name, {})[ch] = vals
    d = agg.get(name, {})
    for ch in ("stored", "euro"):
        if "raw" in d and ch in d and len(d["raw"]) == len(d[ch]):
            diff = np.array(d[ch]) - np.array(d["raw"])
            print(f"{'':<36}{ch + ' - raw':<10}" + " ".join(f"{v:6.0f}" for v in diff)
                  + f"    mean {diff.mean():+.0f} mm")
    print()

print("Error against the RAW channel, which is the measurement both filters")
print("are approximations of:")
for ch in ("stored", "euro"):
    d = [np.array(v[ch]) - np.array(v["raw"]) for v in agg.values()
         if "raw" in v and ch in v and len(v["raw"]) == len(v[ch])]
    if d:
        c = np.concatenate(d)
        print(f"  {ch:<8} mean {c.mean():+6.1f} mm   sd {c.std():5.1f} mm   "
              f"worst |{np.abs(c).max():.0f}| mm   n={len(c)}")
