"""Offline validation of the kinematic-fitting stage."""
from __future__ import annotations
import json
import numpy as np

import metrics as M
from synthetic_squat import make_session
from pose_to_unity import (segment_axes, to_unity_point, to_unity_vec,
                           basis_from, basis_to_quat, PoseStreamer,
                           SEGMENT_ORDER, L_ELB, R_ELB, L_WRI, R_WRI,
                           mirror_kp)

CHAIN = {
    "left_hip":       (M.L_HIP, M.L_KNE),
    "left_knee":      (M.L_KNE, M.L_ANK),
    "right_hip":      (M.R_HIP, M.R_KNE),
    "right_knee":     (M.R_KNE, M.R_ANK),
    "left_shoulder":  (M.L_SHO, L_ELB),
    "left_elbow":     (L_ELB, L_WRI),
    "right_shoulder": (M.R_SHO, R_ELB),
    "right_elbow":    (R_ELB, R_WRI),
    "spine1":         (None, None),
}


def main():
    frames = make_session(noise_mm=0.0)
    stand = [kp for kp, _ in frames[:25]]
    frame = M.calibrate_body_frame(stand)
    origin = PoseStreamer.floor_origin(stand, frame)

    ref = stand[-1]
    lengths = {name: float(np.linalg.norm(ref[b] - ref[a]))
               for name, (a, b) in CHAIN.items() if a is not None}
    lengths["spine1"] = float(np.linalg.norm(
        M._mid(ref[M.L_SHO], ref[M.R_SHO]) - M._mid(ref[M.L_HIP], ref[M.R_HIP])))

    exact, rigid, drift, n_missing = [], [], [], 0
    for kp, _ in frames:
        if not np.isfinite(kp).any():
            continue
        axes = segment_axes(kp, frame)
        for name, (a, b) in CHAIN.items():
            if name not in axes:
                n_missing += 1
                continue
            e_long = axes[name][0]
            if name == "spine1":
                q0 = M._mid(kp[M.L_HIP], kp[M.R_HIP])
                q1 = M._mid(kp[M.L_SHO], kp[M.R_SHO])
            else:
                q0, q1 = kp[a], kp[b]
            p0 = to_unity_point(q0, frame, origin)
            p1 = to_unity_point(q1, frame, origin)
            L_now = float(np.linalg.norm(q1 - q0))
            exact.append(np.linalg.norm(p0 + e_long * (L_now * 0.001) - p1) * 1000.0)
            rigid.append(np.linalg.norm(p0 + e_long * (lengths[name] * 0.001) - p1) * 1000.0)
            drift.append(abs(L_now - lengths[name]))
    exact, rigid, drift = map(np.asarray, (exact, rigid, drift))
    print(f"1. reconstruction from the fitted orientations, {len(exact)} segment-frames "
          f"({n_missing} unresolved)")
    print(f"   with each segment's own length : mean {exact.mean():.2e} mm  "
          f"max {exact.max():.2e} mm")
    assert exact.max() < 1e-6, "orientations do not reproduce the measured skeleton"
    print(f"   with fixed standing lengths    : mean {rigid.mean():.2f} mm  "
          f"max {rigid.max():.2f} mm")
    print(f"   segment-length drift in the data: max {drift.max():.2f} mm "
          f"-> the fixed-length residual is bone-length variation, not fitting error")
    assert abs(rigid.max() - drift.max()) < 1e-3

    worst_dot, worst_norm = 0.0, 0.0
    for kp, _ in frames:
        if not np.isfinite(kp).any():
            continue
        for name, (e1, e2) in segment_axes(kp, frame).items():
            e3 = np.cross(e1, e2)
            worst_dot = max(worst_dot, abs(float(np.dot(e1, e2))))
            worst_norm = max(worst_norm, abs(np.linalg.norm(e1) - 1),
                             abs(np.linalg.norm(e2) - 1), abs(np.linalg.norm(e3) - 1))
            q = basis_to_quat(e1, e2, e3)
            assert abs(np.linalg.norm(q) - 1) < 1e-6, name
    print(f"2. every segment frame orthonormal: max |e1.e2| = {worst_dot:.2e}, "
          f"max |‖e‖-1| = {worst_norm:.2e}")
    assert worst_dot < 1e-9 and worst_norm < 1e-9

    kp = stand[-1]
    lx = to_unity_point(kp[M.L_ANK], frame, origin)[0]
    rx = to_unity_point(kp[M.R_ANK], frame, origin)[0]
    print(f"3. chirality: left ankle x={lx:+.3f} m, right ankle x={rx:+.3f} m "
          f"(left must be -X, or the avatar mirrors the subject)")
    assert lx < 0 < rx

    prev, worst = {}, (0.0, "")
    for kp, _ in frames:
        if not np.isfinite(kp).any():
            prev = {}
            continue
        for name, (e1, e2) in segment_axes(kp, frame).items():
            if name in prev:
                d1 = np.degrees(np.arccos(np.clip(np.dot(e1, prev[name][0]), -1, 1)))
                d2 = np.degrees(np.arccos(np.clip(np.dot(e2, prev[name][1]), -1, 1)))
                if max(d1, d2) > worst[0]:
                    worst = (max(d1, d2), name)
            prev[name] = (e1, e2)
    print(f"4. largest frame-to-frame axis change: {worst[0]:.1f} deg on '{worst[1]}' "
          f"(a flip would show as ~90-180 deg)")
    assert worst[0] < 45.0, f"discontinuity in {worst[1]} — a reference axis flipped"

    s = PoseStreamer(frame, origin=origin, target="parallel")
    pkt = s.packet(stand[-1], 1.0,
                   state={"phase": "SETUP", "rep_count": 0, "live_cue": None,
                          "knee_angle": 173.0, "pelvis_h": 900.0})
    raw = json.dumps(pkt)
    back = json.loads(raw)
    missing = [k for k in ("seq", "t", "present", "root", "seg", "state") if k not in back]
    print(f"5. packet {len(raw)} bytes, {len(back['seg'])}/{len(SEGMENT_ORDER)} segments, "
          f"keys missing: {missing or 'none'}")
    assert not missing and len(raw) < 8000
    assert back["state"]["depth_target"]["name"] == "parallel"

    hurt = stand[-1].copy()
    hurt[M.L_ANK] = np.nan
    axes = segment_axes(hurt, frame)
    print(f"6. with the left ankle occluded: {len(axes)} segments still resolved "
          f"(left_knee correctly dropped: {'left_knee' not in axes})")
    assert "left_knee" not in axes and "left_hip" in axes and "right_knee" in axes
    blank = np.full((17, 3), np.nan)
    assert s.packet(blank, 2.0)["present"] == 0
    print("   all-NaN frame -> present=0, renderer holds the last pose")

    true = PoseStreamer(frame, origin=origin, target="parallel", mirror=False)
    mir = PoseStreamer(frame, origin=origin, target="parallel", mirror=True)
    kp = frames[len(frames) // 2][0].copy()
    kp[M.L_KNE] = kp[M.L_KNE] + frame.lateral * 60.0
    swap = [0, 2, 1, 4, 3, 6, 5, 8, 7, 10, 9, 12, 11, 14, 13, 16, 15]
    arr = lambda j: np.array([[np.nan] * 3 if q is None else q for q in j], float)

    pt, pm = true.packet(kp, 1.0), mir.packet(kp, 1.0)
    jt, jm = arr(pt["joints"]), arr(pm["joints"])
    err = np.nanmax(np.abs(jm - jt[swap] * [-1, 1, 1]))
    print(f"7. mirror: every joint is the opposite-side one reflected in x, "
          f"max error {err * 1000:.4f} mm")
    assert err < 1e-6
    assert pm["mirror"] == 1 and pt["mirror"] == 0

    worst, moved = 0.0, 0.0
    for name in SEGMENT_ORDER:
        if not name.startswith("left_"):
            continue
        other = "right_" + name[5:]
        a, b = np.array(pt["seg"][name][:3]), np.array(pm["seg"][other][:3])
        worst = max(worst, np.abs(b - a * [-1, 1, 1]).max())
        moved = max(moved, np.abs(b - np.array(pt["seg"][other][:3])).max())
    print(f"   each left segment reappears as the avatar's right, reflected "
          f"(max error {worst:.1e}; differs from the unmirrored right by {moved:.2f})")
    assert worst < 1e-3 and moved > 0.05

    for lg, rf in segment_axes(mirror_kp(kp, frame, origin), frame).values():
        assert abs(float(np.dot(lg, rf))) < 1e-9
        assert abs(np.linalg.norm(np.cross(lg, rf)) - 1) < 1e-9
    print(f"   mirrored left-ankle x = {jm[M.L_ANK][0]:+.3f} m — the subject's RIGHT "
          f"ankle, on -X, which is the right of the screen")
    assert abs(jm[M.L_ANK][0] + jt[M.R_ANK][0]) < 1e-6

    print("\nALL CHECKS PASSED")


if __name__ == "__main__":
    main()
