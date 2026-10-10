"""Replay a recorded session's joints as CALIB packets, so the Unity setup skeleton can be built and checked away from the rig."""
import argparse
import glob
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "src"))
from pose_to_unity import PoseStreamer
from session_io import load_session_arrays


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", help="a recorded set (.npz), or a folder holding one")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5006)
    ap.add_argument("--fps", type=float, default=10.0)
    ap.add_argument("--countdown", type=float, default=0.0,
                    help="seconds of count-in to fake before the frames start")
    ap.add_argument("--loop", action="store_true")
    a = ap.parse_args()

    path = a.path
    if os.path.isdir(path):
        found = sorted(glob.glob(os.path.join(path, "**", "*.npz"), recursive=True))
        if not found:
            sys.exit(f"no .npz under {path}")
        path = found[0]
    kp = load_session_arrays(path)["kp"]
    print(f"{os.path.basename(path)}: {len(kp)} frames -> CALIB packets on "
          f"{a.host}:{a.port} at {a.fps:.0f} fps.  Ctrl-C to stop.")

    st = PoseStreamer(None, a.host, a.port, mirror=True)
    dt = 1.0 / max(a.fps, 0.1)
    conf = np.ones((3, 17))
    conf[2, 13:] = 0.2

    try:
        while True:
            t0 = time.time()
            if a.countdown > 0:
                for rem in range(int(a.countdown), 0, -1):
                    for _ in range(int(a.fps)):
                        st.send_setup_pose(kp[0], time.time(), conf=conf,
                                           cams=[0, 1, 2], countdown=rem,
                                           note="hold still")
                        time.sleep(dt)
            for i, k in enumerate(kp):
                st.send_setup_pose(k, time.time(), conf=conf, cams=[0, 1, 2],
                                   note="stand where all three cameras see you")
                time.sleep(dt)
            print(f"  one pass in {time.time() - t0:.1f} s")
            if not a.loop:
                break
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
