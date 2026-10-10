"""Check that the arm you raise shows up on the correct side of the screen."""
from __future__ import annotations
import argparse
import json
import socket
import time

import numpy as np

L_WRI, R_WRI = 9, 10
L_ANK, R_ANK = 15, 16


def screen_side(x):
    """Unity -X is the right of the screen: the camera looks back down -Z."""
    return "RIGHT" if x < 0 else "LEFT"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", default="right", choices=["left", "right"],
                    help="which of YOUR arms you are holding up")
    ap.add_argument("--port", type=int, default=5006)
    ap.add_argument("--seconds", type=float, default=6.0)
    a = ap.parse_args()

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.bind(("127.0.0.1", a.port))
    except OSError as e:
        print(f"Cannot listen on {a.port}: {e}")
        print("Unity in Play mode already holds the port. Stop Play and run this instead.")
        return
    s.settimeout(1.0)
    print(f"Listening {a.seconds:.0f}s. Face the cameras and hold your {a.arm.upper()} "
          f"arm out to the side.\n")

    rows, mirror, t0 = [], None, time.time()
    while time.time() - t0 < a.seconds:
        try:
            data, _ = s.recvfrom(65535)
        except socket.timeout:
            continue
        pkt = json.loads(data)
        j = pkt.get("joints")
        if not j:
            continue
        need = [j[i] for i in (L_WRI, R_WRI, L_ANK, R_ANK)]
        if any(p is None for p in need):
            continue
        mirror = pkt.get("mirror")
        rows.append([c for p in need for c in p])

    if len(rows) < 5:
        print(f"Only {len(rows)} usable frames. Is live_form_feedback.py running with "
              f"--stream, and are you in view?")
        return

    m = np.median(np.asarray(rows, float), axis=0).reshape(4, 3)
    lw, rw, lank, rank = m
    view = ("gym mirror" if mirror else "facing partner (true anatomy)"
            if mirror == 0 else "UNKNOWN — the stream is from an older build")
    print(f"frames used: {len(rows)}   view: {view}")
    print(f"  wrists  x={lw[0]:+.3f}/{rw[0]:+.3f}   y={lw[1]:+.3f}/{rw[1]:+.3f}")
    print(f"  ankles  x={lank[0]:+.3f}/{rank[0]:+.3f}\n")

    if abs(lw[1] - rw[1]) < 0.15:
        print("[??] neither wrist is clearly raised — hold one arm out and run it again")
        return

    x = lw[0] if lw[1] > rw[1] else rw[0]
    shown = screen_side(x)
    want = a.arm.upper() if mirror else ("LEFT" if a.arm == "right" else "RIGHT")
    ok = shown == want
    print(f"[{'OK' if ok else 'FAIL'}] you raised your {a.arm.upper()} arm and it is "
          f"drawn on the {shown} of the screen (expected {want})")
    if ok and mirror:
        print("     Mirrored as intended — it is the avatar's own opposite-side arm, "
              "which is what a gym mirror shows.")
    elif not ok:
        print("     The view is inverted. Check the --no-mirror flag before changing "
              "any sign in pose_to_unity.py.")


if __name__ == "__main__":
    main()
