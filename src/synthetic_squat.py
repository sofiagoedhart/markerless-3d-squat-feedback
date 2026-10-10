"""Generate a fake but anatomically plausible squat sequence for testing without cameras."""
from __future__ import annotations
import numpy as np

NOSE = 0
L_SHO, R_SHO = 5, 6
L_ELB, R_ELB = 7, 8
L_WRI, R_WRI = 9, 10
L_HIP, R_HIP = 11, 12
L_KNE, R_KNE = 13, 14
L_ANK, R_ANK = 15, 16

SHANK, THIGH, TORSO = 430.0, 430.0, 550.0
UPPER_ARM, FOREARM = 300.0, 260.0

HIP_H, SHO_H, ANK_H = 90.0, 190.0, 210.0

STANCE_WIDE = 1.40

STAND = dict(shank_lean=2, thigh_horiz=85, torso_lean=3)
BOTTOMS = {
    "partial": dict(shank_lean=12, thigh_horiz=26,  torso_lean=22),
    "parallel": dict(shank_lean=26, thigh_horiz=11, torso_lean=38),
    "deep":    dict(shank_lean=36, thigh_horiz=-20, torso_lean=44),
}


def _d(x):
    return np.deg2rad(x)


def pose(shank_lean, thigh_horiz, torso_lean, kneeL_medial=0.0, shL_raise=0.0,
         stance=1.0):
    """One skeleton in a LOCAL frame: axis0 = subject's left, axis1 = forward, axis2 = up."""
    A = np.array([0.0, 0.0])
    K = A + SHANK * np.array([np.sin(_d(shank_lean)), np.cos(_d(shank_lean))])
    H = K + THIGH * np.array([-np.cos(_d(thigh_horiz)), np.sin(_d(thigh_horiz))])
    S = H + TORSO * np.array([np.sin(_d(torso_lean)), np.cos(_d(torso_lean))])
    Hd = S + 250 * np.array([np.sin(_d(torso_lean)), np.cos(_d(torso_lean))])

    ank_h = ANK_H * stance
    knee_h = 0.5 * (HIP_H + ank_h)

    kp = np.full((17, 3), np.nan)

    def put(idx, fu, x):
        kp[idx] = [x, fu[0], fu[1]]

    put(L_ANK, A, +ank_h);                   put(R_ANK, A, -ank_h)
    put(L_KNE, K, +knee_h - kneeL_medial);   put(R_KNE, K, -knee_h)
    put(L_HIP, H, +HIP_H);                   put(R_HIP, H, -HIP_H)
    put(L_SHO, S, +SHO_H);                   put(R_SHO, S, -SHO_H)
    kp[L_SHO, 2] += shL_raise
    kp[NOSE] = [0.0, Hd[0], Hd[1]]

    for sho, elb, wri, s_ in ((L_SHO, L_ELB, L_WRI, +1.0), (R_SHO, R_ELB, R_WRI, -1.0)):
        ua = np.array([s_ * 0.50, -0.15, -0.85]);  ua /= np.linalg.norm(ua)
        fa = np.array([-s_ * 0.35, -0.25, 0.90]);  fa /= np.linalg.norm(fa)
        kp[elb] = kp[sho] + UPPER_ARM * ua
        kp[wri] = kp[elb] + FOREARM * fa
    return kp


def _rot(rx, ry, rz):
    Rx = np.array([[1, 0, 0], [0, np.cos(rx), -np.sin(rx)], [0, np.sin(rx), np.cos(rx)]])
    Ry = np.array([[np.cos(ry), 0, np.sin(ry)], [0, 1, 0], [-np.sin(ry), 0, np.cos(ry)]])
    Rz = np.array([[np.cos(rz), -np.sin(rz), 0], [np.sin(rz), np.cos(rz), 0], [0, 0, 1]])
    return Rz @ Ry @ Rx


WORLD_R = _rot(_d(30), _d(20), _d(40))
WORLD_T = np.array([1200.0, -800.0, 2500.0])


def _worldize(kp, R=WORLD_R, T=WORLD_T):
    out = kp.copy()
    ok = np.all(np.isfinite(kp), axis=1)
    out[ok] = kp[ok] @ R.T + T
    return out


def _lerp(a, b, u):
    return {k: (1 - u) * a[k] + u * b[k] for k in a}


def make_session(reps=("partial", "parallel", "deep"), fps=10.0,
                 pre_wide_s=4.0, pre_move_s=1.5, pre_good_s=6.0, tail_s=3.5,
                 half_rep_frames=8, hold_frames=4, bottom_hold_frames=5,
                 knee_cave_mm=110.0, shoulder_raise_mm=80.0,
                 noise_mm=0.0, dropout=True, seed=0) -> list:
    """[(kp (17,3) world mm, t seconds), ...] — a full session, in the order the interface expects to see one."""
    rng = np.random.default_rng(seed)
    dt = 1.0 / fps
    frames, t = [], 0.0

    def add(p):
        nonlocal t
        kp = _worldize(p)
        if noise_mm > 0:
            kp = kp + rng.normal(0, noise_mm, kp.shape)
        frames.append((kp, t))
        t += dt

    n = lambda secs: max(0, int(round(secs * fps)))

    for _ in range(n(pre_wide_s)):
        add(pose(**STAND, stance=STANCE_WIDE))
    for u in np.linspace(0, 1, max(n(pre_move_s), 1) + 1)[1:]:
        add(pose(**STAND, stance=STANCE_WIDE + (1.0 - STANCE_WIDE) * u))
    for _ in range(n(pre_good_s)):
        add(pose(**STAND, stance=1.0))

    for name in reps:
        bottom = BOTTOMS[name]
        for _ in range(hold_frames):
            add(pose(**STAND, stance=1.0))
        for u in np.concatenate([np.linspace(0, 1, half_rep_frames + 1)[1:],
                                 np.ones(bottom_hold_frames),
                                 np.linspace(1, 0, half_rep_frames + 1)[1:]]):
            p = _lerp(STAND, bottom, u)
            add(pose(**p, stance=1.0,
                     kneeL_medial=knee_cave_mm * u if name == "parallel" else 0.0,
                     shL_raise=shoulder_raise_mm * u if name == "deep" else 0.0))

    for _ in range(n(tail_s)):
        add(pose(**STAND, stance=1.0))

    if dropout and len(frames) > 8:
        i = min(6, len(frames) - 1)
        frames.insert(i, (np.full((17, 3), np.nan), frames[i][1]))
    return frames


if __name__ == "__main__":
    f = make_session()
    kp = f[0][0]
    print(f"{len(f)} frames, {f[-1][1]:.1f} s")
    used = [NOSE, L_SHO, R_SHO, L_ELB, R_ELB, L_WRI, R_WRI,
            L_HIP, R_HIP, L_KNE, R_KNE, L_ANK, R_ANK]
    print("all used joints finite in frame 0:", bool(np.isfinite(kp[used]).all()),
          "(eyes/ears 1-4 are intentionally NaN, as YOLO's are unused)")
    print("standing height (mm):", round(float(np.linalg.norm(kp[NOSE] - kp[L_ANK])), 1))
