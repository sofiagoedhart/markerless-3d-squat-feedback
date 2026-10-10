"""Synthetic validation of metrics.py and rep_engine.py."""
import numpy as np
import metrics as M
from rep_engine import SquatRepEngine

L_SHO, R_SHO = 5, 6
L_HIP, R_HIP = 11, 12
L_KNE, R_KNE = 13, 14
L_ANK, R_ANK = 15, 16
LSH, LTH, LTO = 430.0, 430.0, 550.0

def deg(x): return np.deg2rad(x)

def pose(shank_lean, thigh_horiz, torso_lean, kneeL_medial=0.0, shL_raise=0.0):
    A = np.array([0.0, 0.0])
    K = A + LSH * np.array([np.sin(deg(shank_lean)), np.cos(deg(shank_lean))])
    H = K + LTH * np.array([-np.cos(deg(thigh_horiz)), np.sin(deg(thigh_horiz))])
    S = H + LTO * np.array([np.sin(deg(torso_lean)), np.cos(deg(torso_lean))])
    Hd = S + 250 * np.array([np.sin(deg(torso_lean)), np.cos(deg(torso_lean))])
    kp = np.full((17, 3), np.nan)
    def put(idx, yz, x):
        kp[idx] = [x, yz[0], yz[1]]
    put(L_ANK, A, +175); put(R_ANK, A, -175)
    put(L_KNE, K, +160 - kneeL_medial); put(R_KNE, K, -160)
    put(L_HIP, H, +140); put(R_HIP, H, -140)
    put(L_SHO, S, +200); put(R_SHO, S, -200)
    kp[L_SHO, 2] += shL_raise
    kp[0] = [0.0, Hd[0], Hd[1]]
    return kp

STAND = dict(shank_lean=2, thigh_horiz=85, torso_lean=3)
BOTTOMS = {
    "partial": dict(shank_lean=12, thigh_horiz=26, torso_lean=22),
    "normal":  dict(shank_lean=26, thigh_horiz=0,  torso_lean=38),
    "deep":    dict(shank_lean=36, thigh_horiz=-20, torso_lean=44),
}

def lerp(a, b, u): return {k: (1 - u) * a[k] + u * b[k] for k in a}

def rot(rx, ry, rz):
    Rx = np.array([[1,0,0],[0,np.cos(rx),-np.sin(rx)],[0,np.sin(rx),np.cos(rx)]])
    Ry = np.array([[np.cos(ry),0,np.sin(ry)],[0,1,0],[-np.sin(ry),0,np.cos(ry)]])
    Rz = np.array([[np.cos(rz),-np.sin(rz),0],[np.sin(rz),np.cos(rz),0],[0,0,1]])
    return Rz @ Ry @ Rx
R = rot(deg(30), deg(20), deg(40))

def worldize(kp):
    out = kp.copy()
    for i in range(17):
        if np.all(np.isfinite(kp[i])):
            out[i] = R @ kp[i]
    return out

frames = []
dt = 0.1
t = 0.0
for _ in range(30):
    frames.append((worldize(pose(**STAND)), t)); t += dt
for name in ("partial", "normal", "deep"):
    for _ in range(4):
        frames.append((worldize(pose(**STAND)), t)); t += dt
    for u in np.linspace(0, 1, 9)[1:]:
        p = lerp(STAND, BOTTOMS[name], u)
        kneeL = 90.0 * u if name == "normal" else 0.0
        shL = 80.0 * u if name == "deep" else 0.0
        frames.append((worldize(pose(**p, kneeL_medial=kneeL, shL_raise=shL)), t)); t += dt
    for u in np.linspace(1, 0, 9)[1:]:
        p = lerp(STAND, BOTTOMS[name], u)
        kneeL = 90.0 * u if name == "normal" else 0.0
        shL = 80.0 * u if name == "deep" else 0.0
        frames.append((worldize(pose(**p, kneeL_medial=kneeL, shL_raise=shL)), t)); t += dt
frames.insert(60, (np.full((17, 3), np.nan), frames[60][1]))

frame = M.calibrate_body_frame([kp for kp, _ in frames[:30]])
print("up axis (world):", np.round(frame.up, 3))
eng = SquatRepEngine(frame, target="parallel", stance_kp=frames[0][0])

phases = set()
reports = []
for kp, tt in frames:
    st = eng.update(kp, tt)
    phases.add(st["phase"])
    if st["rep_completed"]:
        r = st["last_rep"]
        reports.append(r)
        print(f"REP {r['rep']}: target={r['target_depth']:6s} did={r['variation']:7s} "
              f"met={str(r['depth_met']):5s} dom={r['dominance']:12s} "
              f"valgus={r['valgus']}({r['valgus_s']}s, {r['valgus_dev_mm']}mm) "
              f"kneeSym={r['symmetry_deg']:.0f} shTilt={r['shoulder_tilt_deg']:.0f} "
              f"T-T={r['trunk_tibia_deg']:+.0f} "
              f"dwell={r['bottom_dwell_s']}s faults={r['faults']}\n"
              f"        traces: depth={len(r['depth_traj'])} sym={len(r['symmetry_traj'])} "
              f"tilt={len(r['shoulder_tilt_traj'])}\n"
              f"        cues: {r['cues']}")

print("phases seen:", phases)
print("final rep count:", eng.rep_count)

assert eng.rep_count == 3, "expected 3 reps"
assert len(reports) == 3, "expected 3 reports"

assert "valgus" in reports[1]["faults"], "rep 2 knee cave not detected"
assert reports[1]["valgus_s"] > 0.3, "rep 2 valgus duration not recorded"
assert not reports[0]["valgus"], "rep 1 should be clean"
assert not reports[2]["valgus"], "rep 3 should have no valgus"
assert abs(reports[2]["shoulder_tilt_deg"]) > 5, "rep 3 shoulder tilt not detected"
assert abs(reports[0]["shoulder_tilt_deg"]) < 3, "rep 1 should have level shoulders"

assert reports[0]["variation"] == "partial", "rep 1 should classify as partial"
assert reports[0]["depth_met"] is False, "rep 1 should be flagged shallow"
assert reports[1]["variation"] == "deep" and reports[1]["depth_met"] == "deeper"
assert reports[2]["variation"] == "deep" and reports[2]["depth_met"] == "deeper"

for i, r in enumerate(reports):
    assert r["depth_traj"] and r["symmetry_traj"] and r["shoulder_tilt_traj"], \
        f"rep {i+1} produced empty trajectories"

print("OK")

tf, t = [], 0.0
for _ in range(30):
    tf.append((worldize(pose(**STAND)), t)); t += dt
for hold in (10, 0):
    for _ in range(4):
        tf.append((worldize(pose(**STAND)), t)); t += dt
    for u in np.linspace(0, 1, 9)[1:]:
        tf.append((worldize(pose(**lerp(STAND, BOTTOMS["normal"], u))), t)); t += dt
    for _ in range(hold):
        tf.append((worldize(pose(**BOTTOMS["normal"])), t)); t += dt
    for u in np.linspace(1, 0, 9)[1:]:
        tf.append((worldize(pose(**lerp(STAND, BOTTOMS["normal"], u))), t)); t += dt
    for _ in range(4):
        tf.append((worldize(pose(**STAND)), t)); t += dt
eng2 = SquatRepEngine(frame, target="parallel", stance_kp=tf[0][0])
tempo, seen = [], set()
for kp, tt in tf:
    st = eng2.update(kp, tt)
    seen.add(st["phase"])
    if st["rep_completed"]:
        tempo.append(st["last_rep"])
for r in tempo:
    print(f"TEMPO rep {r['rep']}: descent={r['descent_s']} dwell={r['bottom_dwell_s']} "
          f"ascent={r['ascent_s']}")
assert len(tempo) == 2, "expected 2 tempo reps"
assert "BOTTOM" in seen, "held bottom never entered BOTTOM"
assert 0.7 <= tempo[0]["bottom_dwell_s"] <= 1.3, "paused rep dwell off"
assert tempo[1]["bottom_dwell_s"] == 0.0, "no-pause rep should have zero dwell"
for r in tempo:
    total = r["descent_s"] + r["bottom_dwell_s"] + r["ascent_s"]
    assert abs(total - (r["t_ascent_s"] + r["ascent_s"])) < 0.02, "segments do not tile the rep"
print("tempo OK")
