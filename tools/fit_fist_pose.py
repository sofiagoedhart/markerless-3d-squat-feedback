"""Fits the fist pose used by HandFist.cs on the SMPL-X template hand skeleton and prints the C# arrays."""
import json
from pathlib import Path
import numpy as np
from scipy.optimize import minimize
from scipy.spatial.transform import Rotation as R

RES = Path(__file__).resolve().parents[1] / "SMPLX-Unity/Assets/SMPLX/Resources"
JS = {g: np.array(json.load(open(RES / f"smplx_betas_to_joints_{g}.json"))["template_J"]) for g in ("female", "male")}
LEFT = {"index": 25, "middle": 28, "pinky": 31, "ring": 34, "thumb": 37}
WRIST = 20
CURL_DEG = {"index": (70, 95, 55), "middle": (78, 98, 55), "ring": (84, 98, 52), "pinky": (90, 95, 50)}
BASE = {f: np.array([[0, 0, -np.radians(a)] for a in c]) for f, c in CURL_DEG.items()}


def fk(J, pose):
    """Forward kinematics of the left hand; returns wrist, joints 1-3 and an extrapolated tip per finger (m)."""
    out = {}
    for f, s in LEFT.items():
        rest = [J[s], J[s + 1], J[s + 2], J[s + 2] + 0.9 * (J[s + 2] - J[s + 1])]
        Rg, pts = np.eye(3), [rest[0]]
        for k in range(3):
            Rg = Rg @ R.from_rotvec(pose[f][k]).as_matrix()
            pts.append(pts[-1] + Rg @ (rest[k + 1] - rest[k]))
        out[f] = np.array([J[WRIST]] + pts)
    return out


def thumb_pose(x, J):
    """Thumb CMC is free (3 DOF); MCP and IP flex about one axis toward the palm."""
    v = J[39] - J[38]
    a = np.cross(v / np.linalg.norm(v), np.array([0, -1, -1]) / np.sqrt(2))
    a /= np.linalg.norm(a)
    return np.array([x[:3], a * x[3], a * x[4]])


def seg_dist(p, a, b):
    t = np.clip(np.dot(p - a, b - a) / np.dot(b - a, b - a), 0, 1)
    return np.linalg.norm(p - (a + t * (b - a)))


def parts(x, J):
    """Thumb-tip error to its target beside the index middle phalanx, and thumb clearance from index/middle (m)."""
    pose = dict(BASE, thumb=thumb_pose(x, J))
    o = fk(J, pose)
    target = (o["index"][2] + o["index"][3]) / 2 + np.array([0.006, 0.0, 0.013])
    T = o["thumb"]
    pts = [T[2], (T[2] + T[3]) / 2, T[3], (T[3] + T[4]) / 2, T[4]]
    clear = min(seg_dist(s, o[f][k], o[f][k + 1]) for f in ("index", "middle") for k in range(1, 4) for s in pts)
    return np.linalg.norm(T[4] - target), clear


def cost(x, J):
    e, c = parts(x, J)
    return e ** 2 * 1e4 + max(0, 0.014 - c) ** 2 * 1e6 + 2e-3 * np.sum(x[:3] ** 2)


if __name__ == "__main__":
    bounds = [(-1.5, 1.5)] * 3 + [(0, 1.4), (0, 1.4)]
    both = lambda x: cost(x, JS["female"]) + cost(x, JS["male"])
    best = None
    for s in range(40):
        rs = np.random.RandomState(s)
        r = minimize(both, np.r_[rs.uniform(-1.2, 1.2, 3), rs.uniform(0, 1.2, 2)], method="Powell",
                     bounds=bounds, options={"maxiter": 20000})
        if best is None or r.fun < best.fun:
            best = r
    for g, J in JS.items():
        e, c = parts(best.x, J)
        print(f"{g}: thumb tip {e * 1000:.1f} mm from target, clearance {c * 1000:.1f} mm")
    pose = dict(BASE, thumb=thumb_pose(best.x, JS["female"]))
    left = np.concatenate([pose[f].ravel() for f in ("index", "middle", "pinky", "ring", "thumb")])
    print("LEFT_FIST =", ", ".join(f"{v:.3f}f" for v in left))
