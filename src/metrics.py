"""Joint-angle and geometry primitives for the squat form-feedback system."""
from __future__ import annotations
import numpy as np
from dataclasses import dataclass

NOSE = 0
L_SHO, R_SHO = 5, 6
L_HIP, R_HIP = 11, 12
L_KNE, R_KNE = 13, 14
L_ANK, R_ANK = 15, 16


def _ok(*pts) -> bool:
    """True if every given point is finite."""
    return all(np.all(np.isfinite(p)) for p in pts)


def _mid(a, b):
    """Midpoint of two joints."""
    return (a + b) / 2.0


def angle_at(a, b, c) -> float:
    """Interior angle at vertex b of a-b-c, in degrees."""
    a, b, c = np.asarray(a, float), np.asarray(b, float), np.asarray(c, float)
    if not _ok(a, b, c):
        return np.nan
    ba, bc = a - b, c - b
    nba, nbc = np.linalg.norm(ba), np.linalg.norm(bc)
    if nba < 1e-6 or nbc < 1e-6:
        return np.nan
    return float(np.degrees(np.arccos(np.clip(np.dot(ba, bc) / (nba * nbc), -1, 1))))


@dataclass
class BodyFrame:
    """Orthonormal body-relative axes: up, lateral (right to left), forward."""
    up: np.ndarray
    lateral: np.ndarray
    forward: np.ndarray

    def height(self, p) -> float:
        """Position of p along the up axis, in mm."""
        return float(np.dot(np.asarray(p, float), self.up))

    def sagittal(self, v):
        """Component of v in the sagittal plane."""
        v = np.asarray(v, float)
        return v - np.dot(v, self.lateral) * self.lateral


def calibrate_body_frame(standing_skeletons, fixed_up=None) -> BodyFrame:
    """Build a BodyFrame from several frames of a still, upright stand: up is `fixed_up` or mid-ankle to mid-shoulder, lateral is right hip to left hip orthogonalised to up, and forward is up x lateral."""
    ups, lats = [], []
    for kp in standing_skeletons:
        kp = np.asarray(kp, float)
        msho, mank = _mid(kp[L_SHO], kp[R_SHO]), _mid(kp[L_ANK], kp[R_ANK])
        if _ok(msho, mank):
            ups.append(msho - mank)
        if _ok(kp[L_HIP], kp[R_HIP]):
            lats.append(kp[L_HIP] - kp[R_HIP])
    if not lats or (fixed_up is None and not ups):
        raise ValueError("calibration failed: not enough clean standing frames")
    up = np.asarray(fixed_up, float) if fixed_up is not None else np.mean(ups, axis=0)
    up = up / np.linalg.norm(up)
    lat = np.mean(lats, axis=0)
    lat = lat - np.dot(lat, up) * up
    lat /= np.linalg.norm(lat)
    fwd = np.cross(up, lat); fwd /= np.linalg.norm(fwd)
    faces = []
    for kp in standing_skeletons:
        kp = np.asarray(kp, float)
        mhip = _mid(kp[L_HIP], kp[R_HIP])
        if _ok(kp[NOSE], mhip):
            faces.append(kp[NOSE] - mhip)
    if faces:
        face = np.mean(faces, axis=0)
        face = face - np.dot(face, up) * up
        if np.linalg.norm(face) > 1e-6 and np.dot(fwd, face) < 0:
            fwd = -fwd
    return BodyFrame(up=up, lateral=lat, forward=fwd)


def knee_angles(kp):
    """Left and right interior knee angles, in degrees."""
    return (angle_at(kp[L_HIP], kp[L_KNE], kp[L_ANK]),
            angle_at(kp[R_HIP], kp[R_KNE], kp[R_ANK]))


def knee_signal(kp) -> float:
    """Mean interior knee angle, in degrees."""
    L, R = knee_angles(kp)
    vals = [v for v in (L, R) if np.isfinite(v)]
    return float(np.mean(vals)) if vals else np.nan


def pelvis_height(kp, frame: BodyFrame) -> float:
    """Height of the mid-hip along the up axis, in mm."""
    mhip = _mid(kp[L_HIP], kp[R_HIP])
    return frame.height(mhip) if _ok(mhip) else np.nan


def depth_margin(kp, frame: BodyFrame) -> float:
    """Mid-hip height minus mid-knee height along the up axis, in mm."""
    mhip, mknee = _mid(kp[L_HIP], kp[R_HIP]), _mid(kp[L_KNE], kp[R_KNE])
    if not _ok(mhip, mknee):
        return np.nan
    return frame.height(mhip) - frame.height(mknee)


def _incline_from_up(vec, frame, sagittal=False) -> float:
    """Inclination of a segment from vertical, in degrees."""
    vec = np.asarray(vec, float)
    if sagittal:
        fwd = float(np.dot(vec, frame.forward))
        up = float(np.dot(vec, frame.up))
        if abs(fwd) < 1e-9 and abs(up) < 1e-9:
            return np.nan
        return float(np.degrees(np.arctan2(fwd, up)))
    n = np.linalg.norm(vec)
    if n < 1e-6:
        return np.nan
    return float(np.degrees(np.arccos(np.clip(np.dot(vec, frame.up) / n, -1, 1))))


def trunk_incline(kp, frame: BodyFrame, sagittal=False) -> float:
    """Trunk inclination from vertical, mid-hip to mid-shoulder, in degrees."""
    mhip, msho = _mid(kp[L_HIP], kp[R_HIP]), _mid(kp[L_SHO], kp[R_SHO])
    if not _ok(mhip, msho):
        return np.nan
    return _incline_from_up(msho - mhip, frame, sagittal)


def tibia_incline(kp, frame: BodyFrame, sagittal=False) -> float:
    """Tibial inclination from vertical, in degrees, averaged over both legs."""
    vals = []
    for a, k in ((L_ANK, L_KNE), (R_ANK, R_KNE)):
        if _ok(kp[a], kp[k]):
            v = _incline_from_up(kp[k] - kp[a], frame, sagittal)
            if np.isfinite(v):
                vals.append(v)
    return float(np.mean(vals)) if vals else np.nan


def trunk_tibia_angle(kp, frame: BodyFrame) -> float:
    """Trunk inclination minus tibial inclination, sagittal plane, in degrees."""
    t = trunk_incline(kp, frame, sagittal=True)
    s = tibia_incline(kp, frame, sagittal=True)
    if not (np.isfinite(t) and np.isfinite(s)):
        return np.nan
    return float(t - s)


def squat_dominance(trunk_tibia_deg, centre=-16.25, band=3.86) -> str:
    """Classify the trunk-tibia difference as hip-dominant (above centre + band), knee-dominant (below centre - band) or balanced."""
    d = trunk_tibia_deg
    if not np.isfinite(d):
        return "unknown"
    if d > centre + band:
        return "hip-dominant"
    if d < centre - band:
        return "knee-dominant"
    return "balanced"


def knee_medial_deviation(kp, frame: BodyFrame, side: str) -> float:
    """Signed medial offset of one knee from its hip-ankle line, in mm, measured in the frontal plane as a perpendicular distance."""
    idx = {"L": (L_HIP, L_KNE, L_ANK), "R": (R_HIP, R_KNE, R_ANK)}[side]
    H, K, A = kp[idx[0]], kp[idx[1]], kp[idx[2]]
    if not _ok(H, K, A):
        return np.nan
    f = lambda p: np.array([np.dot(p, frame.lateral), np.dot(p, frame.up)], float)
    hf, kf, af = f(H), f(K), f(A)
    d = af - hf
    dd = float(np.dot(d, d))
    if dd < 1e-6:
        return np.nan
    t = float(np.dot(kf - hf, d)) / dd
    closest = hf + t * d
    dev = float((kf - closest)[0])
    return float(-dev if side == "L" else dev)


def shank_length(kp, side: str) -> float:
    """Knee-to-ankle distance for one leg, in mm."""
    a, k = (L_ANK, L_KNE) if side == "L" else (R_ANK, R_KNE)
    if not _ok(kp[a], kp[k]):
        return np.nan
    return float(np.linalg.norm(kp[k] - kp[a]))


def knee_valgus_norm(kp, frame: BodyFrame, side: str) -> float:
    """Medial knee deviation divided by shank length, dimensionless."""
    dev = knee_medial_deviation(kp, frame, side)
    sh = shank_length(kp, side)
    if not (np.isfinite(dev) and np.isfinite(sh) and sh > 1e-6):
        return np.nan
    return float(dev / sh)


def knee_separation(kp, frame: BodyFrame) -> float:
    """Lateral gap between the knees, in mm."""
    kL, kR = kp[L_KNE], kp[R_KNE]
    if not _ok(kL, kR):
        return np.nan
    return float(abs(np.dot(kL - kR, frame.lateral)))


def knee_ankle_sep_ratio(kp, frame: BodyFrame) -> float:
    """Knee separation divided by ankle separation on the lateral axis."""
    kL, kR, aL, aR = kp[L_KNE], kp[R_KNE], kp[L_ANK], kp[R_ANK]
    if not _ok(kL, kR, aL, aR):
        return np.nan
    ksep = abs(np.dot(kL - kR, frame.lateral))
    asep = abs(np.dot(aL - aR, frame.lateral))
    return float(ksep / asep) if asep > 1e-6 else np.nan


def knee_symmetry(kp) -> float:
    """Absolute left-right knee-angle difference, in degrees."""
    L, R = knee_angles(kp)
    if not (np.isfinite(L) and np.isfinite(R)):
        return np.nan
    return float(abs(L - R))


def shoulder_tilt(kp, frame: BodyFrame) -> float:
    """Signed tilt of the shoulder line from horizontal, in degrees."""
    s = kp[L_SHO] - kp[R_SHO]
    n = np.linalg.norm(s)
    if not _ok(kp[L_SHO], kp[R_SHO]) or n < 1e-6:
        return np.nan
    return float(np.degrees(np.arcsin(np.clip(np.dot(s, frame.up) / n, -1, 1))))


def stance_width_ratio(kp, frame: BodyFrame, shoulder_mm=None) -> float:
    """Ankle separation divided by shoulder width on the lateral axis."""
    aL, aR = kp[L_ANK], kp[R_ANK]
    if not _ok(aL, aR):
        return np.nan
    asep = abs(np.dot(aL - aR, frame.lateral))
    if shoulder_mm is not None and np.isfinite(shoulder_mm) and shoulder_mm > 1e-6:
        return float(asep / float(shoulder_mm))
    sL, sR = kp[L_SHO], kp[R_SHO]
    if not _ok(sL, sR):
        return np.nan
    ssep = abs(np.dot(sL - sR, frame.lateral))
    return float(asep / ssep) if ssep > 1e-6 else np.nan


def classify_stance_width(sw, narrow=1.0, wide=1.5):
    """Classify stance width as narrow, medium or wide, with a setup cue."""
    if not np.isfinite(sw):
        return ("unknown", "")
    if sw < narrow:
        return ("narrow", "Your stance is narrow - feet are quite close together - try about shoulder-width apart.")
    if sw > wide:
        return ("wide", "Your stance is quite wide - bring your feet closer in so that they are shoulder-width apart.")
    return ("medium", "Your stance is medium - feet are about shoulder width apart.")
