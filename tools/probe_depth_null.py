"""Replay a recording into Unity with depth_mm forced to null for a window, so the live depth marker can be watched while packets keep arriving."""
from __future__ import annotations
import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
import pose_to_unity
import replay_to_unity

ap = argparse.ArgumentParser()
ap.add_argument("--null-at", type=float, default=4.0,
                help="seconds into the recording at which depth_mm goes null")
ap.add_argument("--null-for", type=float, default=3.0, help="window length, s")
ap.add_argument("--mode", default="depth", choices=["depth", "nostate"],
                help="depth: depth_mm=null, rest intact; "
                     "nostate: drop the whole state block (present stays 1)")
a, rest = ap.parse_known_args()
if rest and rest[0] == "--":
    rest = rest[1:]

_orig = pose_to_unity.PoseStreamer.packet
_t0 = {"t": None, "inside": False, "n": 0}


def _packet(self, kp, t, state=None, rep=None):
    """The real packet, with depth removed inside the window."""
    pkt = _orig(self, kp, t, state, rep)
    if t == 0.0 or "state" not in pkt:
        return pkt
    if _t0["t"] is None or t < _t0["t"]:
        _t0["t"] = t
    rel = t - _t0["t"]
    inside = a.null_at <= rel < a.null_at + a.null_for
    if inside != _t0["inside"]:
        print(f"\n>>> PROBE {'ON ' if inside else 'OFF'} at {rel:.2f} s "
              f"(seq {pkt['seq']}, {a.mode})", flush=True)
        _t0["inside"] = inside
    if inside:
        _t0["n"] += 1
        if a.mode == "depth":
            pkt["state"]["depth_mm"] = None
        else:
            del pkt["state"]
    return pkt


pose_to_unity.PoseStreamer.packet = _packet
sys.argv = [sys.argv[0]] + rest
replay_to_unity.main()
print(f"probe altered {_t0['n']} packets")
