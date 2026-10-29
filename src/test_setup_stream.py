"""Tests for the setup stream sent to Unity before standing calibration."""
import json
import os
import socket
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import metrics as M
import pose_to_unity as P


def standing():
    """A plausible standing skeleton in world mm, up = +Y, ankles at y = 60."""
    kp = np.full((17, 3), np.nan)
    kp[M.NOSE] = (0, 1620, 60)
    kp[1], kp[2] = (40, 1660, 50), (-40, 1660, 50)
    kp[3], kp[4] = (90, 1630, 0), (-90, 1630, 0)
    kp[M.L_SHO], kp[M.R_SHO] = (200, 1400, 0), (-200, 1400, 0)
    kp[7], kp[8] = (340, 1120, 0), (-340, 1120, 0)
    kp[9], kp[10] = (400, 850, 0), (-400, 850, 0)
    kp[M.L_HIP], kp[M.R_HIP] = (100, 900, 0), (-100, 900, 0)
    kp[M.L_KNE], kp[M.R_KNE] = (110, 480, 0), (-110, 480, 0)
    kp[M.L_ANK], kp[M.R_ANK] = (105, 60, 0), (-105, 60, 0)
    return kp


def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    sock.settimeout(2.0)
    port = sock.getsockname()[1]
    st = P.PoseStreamer(None, "127.0.0.1", port, mirror=True)
    kp = standing()

    conf = np.ones((3, 17))
    conf[1, 5:7] = 0.2
    conf[2, 8:] = 0.1

    print("1. a setup packet with NO body frame at all")
    st.send_setup_pose(kp, 123.5, up=[0, 1, 0], conf=conf, cams=[0, 1, 2],
                       countdown=3, note="hold still")
    pkt = json.loads(sock.recv(65535).decode())
    assert st.frame is None, "the streamer must still be uncalibrated"
    assert pkt["phase"] == "CALIB", pkt["phase"]
    assert pkt["present"] == 1
    assert pkt["countdown"] == 3 and pkt["note"] == "hold still"
    assert len(pkt["joints"]) == 17, len(pkt["joints"])
    print("   phase %s, %d joints, countdown %s"
          % (pkt["phase"], len(pkt["joints"]), pkt["countdown"]))

    print("2. the skeleton stands on the floor, not at hip height")
    ys = [j[1] for j in pkt["joints"] if j]
    assert min(ys) < 0.05, min(ys)
    assert 1.4 < max(ys) < 1.9, max(ys)
    print("   lowest joint %.3f m, highest %.3f m" % (min(ys), max(ys)))

    print("3. per-camera joint counts")
    got = {c["cam"]: c["n"] for c in pkt["cams"]}
    assert got == {0: 17, 1: 15, 2: 8}, got
    print("   %s" % got)

    print("4. a missing joint travels as null, not as a wrong number")
    kp2 = kp.copy()
    kp2[M.L_ANK] = np.nan
    st.send_setup_pose(kp2, 124.0, up=[0, 1, 0], conf=conf, cams=[0, 1, 2])
    pkt2 = json.loads(sock.recv(65535).decode())
    assert sum(1 for j in pkt2["joints"] if j is None) == 1
    print("   one null, the rest finite")

    print("5. nobody in the volume")
    st.send_setup_pose(np.full((17, 3), np.nan), 125.0, up=[0, 1, 0])
    pkt3 = json.loads(sock.recv(65535).decode())
    assert pkt3["present"] == 0 and "joints" not in pkt3
    print("   present=0, no joints sent")

    print("6. handover: calibrate(), then the live packet works as before")
    fr = P.setup_frame(kp, up=[0, 1, 0])
    org = M._mid(kp[M.L_ANK], kp[M.R_ANK])
    st.calibrate(fr, origin=org, subject_mm=840.0, shoulder_mm=400.0,
                 limb_mm=P.limb_lengths([kp]))
    live = st.packet(kp, 126.0, state={"phase": "SETUP", "rep_count": 0})
    assert "seg" in live and len(live["seg"]) >= 13, sorted(live.get("seg", {}))
    assert live["subject"]["hip_ankle_mm"] == 840.0
    assert live["state"]["phase"] == "SETUP"
    print("   %d segments, subject %.0f mm, phase %s"
          % (len(live["seg"]), live["subject"]["hip_ankle_mm"],
             live["state"]["phase"]))

    print("7. the sequence number is continuous across the handover")
    assert live["seq"] == 3, live["seq"]
    print("   seq reached %d without restarting" % live["seq"])

    sock.close()
    print("\nALL CHECKS PASSED")


if __name__ == "__main__":
    main()
