"""Squat repetition state machine and per-repetition assessment."""
from __future__ import annotations
import numpy as np
from dataclasses import dataclass, field

import metrics as M

H_DROP_ENTER = 30.0
MIN_KNEE_EXCURSION = 50.0
EPS_KNEE = 10.0
EPS_H = 40.0
V_DEADBAND = 40.0
V_RISE = 60.0
RISE_FRAMES = 2
DWELL_BAND = 40.0

PARALLEL_BAND = 54.95
DEPTH_OFFSET = 95.55
PARTIAL_MAX_MM = 300.0
REF_FEMUR_MM = 433.0
FEMUR_RANGE_MM = (300.0, 600.0)

SHOULDER_EVEN_DEG = 5.0

VALGUS_SEP_DROP_MM = 25.0
VALGUS_FAULT_FRACTION = 0.30
VALGUS_LIVE_FRAMES = 2

UPRIGHT_DEG = 160.0
GAP_WINDOW_S = 3.0
GAP_MIN_S = 1.5
GAP_MIN_FRAMES = 8
GAP_BUF_S = 15.0
GAP_MAD_MM = 15.0
FLEXION_GATE_DEG = 150.0

DOMINANCE_CENTRE = -16.25
DOMINANCE_BAND = 3.86

REQUIRED_JOINTS = (M.L_SHO, M.R_SHO, M.L_HIP, M.R_HIP,
                   M.L_KNE, M.R_KNE, M.L_ANK, M.R_ANK)

REP_ABANDON_S = 1.5
VALGUS_MAX_GAP_S = 0.5

DEPTH_ORDER = {"too_shallow": -1, "partial": 0, "parallel": 1, "deep": 2}

CUES = {
    "valgus": "Push your knees out so they point in the same direction as your toes.",
    "good": "Good rep - your depth and alignment were on target.",
    "depth_unmeasured": (
        "Depth could not be measured. Keep your whole body in view of the cameras "
        "and try again."
    ),
}

DEPTH_CUES = {
    "parallel_shallow": (
        "You stopped above your target depth - "
        "lower your hips until they reach approximately knee height."
    ),
    "deep_shallow": (
        "You stopped above your target depth - lower your hips below knee height."
    ),
    "partial_deeper": (
        "You went deeper than the selected partial squat - stop the descent earlier."
    ),
    "parallel_deeper": (
        "You went deeper than the selected parallel squat - "
        "stop when your hips reach approximately knee height."
    ),
}


def depth_scale(femur_mm=None) -> float:
    """Depth threshold scale for this athlete's femur length, or 1.0 when it is unknown."""
    if femur_mm is None or not np.isfinite(femur_mm):
        return 1.0
    f = float(femur_mm)
    if not (FEMUR_RANGE_MM[0] <= f <= FEMUR_RANGE_MM[1]):
        return 1.0
    return f / REF_FEMUR_MM


def classify_depth(margin_mm, band=PARALLEL_BAND, offset=DEPTH_OFFSET,
                   partial_max=PARTIAL_MAX_MM, femur_mm=None) -> str:
    """Classify a depth margin as too_shallow, partial, parallel or deep."""
    if not np.isfinite(margin_mm):
        return "unknown"
    k = depth_scale(femur_mm)
    band, offset, partial_max = band * k, offset * k, partial_max * k
    m = margin_mm - offset
    if margin_mm > partial_max:
        return "too_shallow"
    if m > band:
        return "partial"
    if m < -band:
        return "deep"
    return "parallel"


def shoulder_band(tilt_deg) -> str:
    """Whether the tilt is inside the reading band or outside it."""
    if not np.isfinite(tilt_deg):
        return "unmeasured"
    return "even" if abs(float(tilt_deg)) <= SHOULDER_EVEN_DEG else "outside"


@dataclass
class RepReport:
    """Per-repetition assessment record."""
    rep: int
    target_depth: str
    variation: str
    depth_met: object
    depth_margin_mm: float
    knee_at_depth: float
    trunk_tibia_deg: float
    dominance: str
    descent_s: float
    ascent_s: float
    bottom_dwell_s: float
    valgus: bool
    valgus_s: float
    valgus_frac: float
    t_bottom_s: float
    t_ascent_s: float
    valgus_t: float
    valgus_peak: float
    valgus_dev_mm: float
    valgus_limit_mm: float
    knee_gap_mm: float
    femur_mm: object
    depth_scale: float
    depth_offset_mm: float
    depth_band_mm: float
    depth_partial_max_mm: float
    symmetry_deg: float
    shoulder_tilt_deg: float
    shoulder_peak_deg: float
    shoulder_tilt0_deg: object
    shoulder_referenced: bool
    shoulder_band: str
    shoulder_even_deg: float
    shoulder_level: bool
    depth_traj: list = field(default_factory=list)
    symmetry_traj: list = field(default_factory=list)
    valgus_traj: list = field(default_factory=list)
    sym_signed_traj: list = field(default_factory=list)
    sym_signed_deg: float = float("nan")
    shoulder_tilt_traj: list = field(default_factory=list)
    faults: list = field(default_factory=list)
    cues: list = field(default_factory=list)

    def as_dict(self):
        """Return the report as a plain dictionary."""
        return self.__dict__.copy()


def _femur_len(kp) -> float:
    """Mean hip-to-knee length over both legs, in mm."""
    out = []
    for h, k in ((M.L_HIP, M.L_KNE), (M.R_HIP, M.R_KNE)):
        a, b = np.asarray(kp[h], float), np.asarray(kp[k], float)
        if np.all(np.isfinite(a)) and np.all(np.isfinite(b)):
            out.append(float(np.linalg.norm(a - b)))
    return float(np.mean(out)) if out else np.nan


def calibration_femur(frames) -> float:
    """Median thigh length over the accepted standing-calibration frames, in mm, or NaN when none of them gives one."""
    v = [_femur_len(np.asarray(kp, float)) for kp in frames]
    v = [x for x in v if np.isfinite(x)]
    return float(np.median(v)) if v else np.nan


def _signed_knee_diff(kp) -> float:
    """Left knee angle minus right."""
    L, R = M.knee_angles(kp)
    return float(L - R) if (np.isfinite(L) and np.isfinite(R)) else np.nan


def valgus_neutral(standing, frame, min_frames=15):
    """The athlete's own knee gap while standing, in mm, which the valgus check is measured against."""
    g = [M.knee_separation(np.asarray(kp, float), frame) for kp in standing]
    g = [v for v in g if np.isfinite(v)]
    if len(g) < min_frames:
        return np.nan, f"only {len(g)} clean standing frames - valgus not referenced"
    gap = float(np.median(g))
    if not (80.0 < gap < 600.0):
        return np.nan, f"standing knee gap {gap:.0f} mm implausible - not referenced"
    return gap, f"standing knee gap {gap:.0f} mm (fault at {gap - VALGUS_SEP_DROP_MM:.0f} mm)"


class SquatRepEngine:
    """Segments the live 3D skeleton into squat repetitions and assesses each one."""

    def __init__(self, body_frame: M.BodyFrame, target="parallel",
                 theta0=None, h0=None, stance_kp=None, shoulder_mm=None,
                 valgus0=None, femur_mm=None):
        self.frame = body_frame
        self.target = target
        self.phase = "SETUP"
        self.rep_count = 0
        self._calibrated = theta0 is not None and h0 is not None
        self._theta0 = float(theta0) if theta0 is not None else None
        self._h0 = float(h0) if h0 is not None else None
        self._base_n = 0
        self._t_prev = None
        self._h_prev = None
        self.stance_width = np.nan
        self.stance_note = ""
        self.shoulder_mm = shoulder_mm
        self._stance_kp = None
        self._valgus_mm = np.nan
        self._gap_buf = []
        self._tilt_buf = []
        self._tilt0 = np.nan
        self.tilt_note = "shoulder baseline not measured yet"
        self._femur_buf = []
        self._femur0 = np.nan
        self.femur_note = "femur not measured yet"
        self._femur_fixed = False
        if (femur_mm is not None and np.isfinite(femur_mm)
                and FEMUR_RANGE_MM[0] <= femur_mm <= FEMUR_RANGE_MM[1]):
            self._femur0 = float(femur_mm)
            self._femur_fixed = True
            self.femur_note = (f"femur {femur_mm:.0f} mm, fixed from calibration "
                               f"(depth thresholds x{femur_mm / REF_FEMUR_MM:.2f})")
        self._t_good = None
        self.abandoned_reps = 0
        self._gap_supplied = False
        self.gap_note = "knee gap not measured yet"
        self._gap_widened = False
        self._gap0 = float(valgus0) if (valgus0 is not None
                                        and np.isfinite(valgus0)) else np.nan
        if stance_kp is not None:
            self._set_stance(stance_kp)
        self._reset_rep()

    def seed_stance(self, kp, t):
        """Add one standing frame to the knee-gap baseline before the set starts."""
        self._gap_push(kp, t)

    def _gap_push(self, kp, t):
        """Keep an upright frame's knee gap, for the baseline."""
        if self._gap_supplied:
            return
        kp = np.asarray(kp, float)
        th = M.knee_signal(kp)
        if not (np.isfinite(th) and th > UPRIGHT_DEG):
            return
        sh = M.shoulder_tilt(kp, self.frame)
        if np.isfinite(sh):
            self._tilt_buf.append((float(t), float(sh)))
            t_cut = self._tilt_buf[-1][0] - GAP_BUF_S
            if self._tilt_buf[0][0] < t_cut:
                self._tilt_buf = [(tt, vv) for tt, vv in self._tilt_buf if tt >= t_cut]
            self._tilt_refresh()
        fm = _femur_len(kp) if not self._femur_fixed else np.nan
        if np.isfinite(fm):
            self._femur_buf.append((float(t), float(fm)))
            t_cut = self._femur_buf[-1][0] - GAP_BUF_S
            if self._femur_buf[0][0] < t_cut:
                self._femur_buf = [(tt, vv) for tt, vv in self._femur_buf
                                   if tt >= t_cut]
            self._femur_refresh()
        g = M.knee_separation(kp, self.frame)
        if np.isfinite(g):
            self._gap_buf.append((float(t), float(g)))
            t_cut = self._gap_buf[-1][0] - GAP_BUF_S
            if self._gap_buf[0][0] < t_cut:
                self._gap_buf = [(tt, gg) for tt, gg in self._gap_buf if tt >= t_cut]
            self._gap_refresh()

    def _gap_refresh(self):
        """Recompute the knee-gap baseline from the most recent standing frames."""
        if not self._gap_buf:
            return
        t_end = self._gap_buf[-1][0]
        win = [(t, g) for t, g in self._gap_buf if t >= t_end - GAP_WINDOW_S]
        span = (win[-1][0] - win[0][0]) if len(win) > 1 else 0.0
        widened = False
        if len(win) < GAP_MIN_FRAMES or span < GAP_MIN_S:
            win = list(self._gap_buf)
        vals = np.array([g for _, g in win], float)
        if vals.size < 3:
            return
        med = float(np.median(vals))
        mad = float(np.median(np.abs(vals - med)))
        if mad > GAP_MAD_MM:
            vals = np.array([g for _, g in self._gap_buf], float)
            med = float(np.median(vals))
            widened = True
        if not (80.0 < med < 600.0):
            return
        self._gap0 = med
        self._gap_widened = widened
        self.gap_note = (f"standing knee gap {med:.0f} mm from {len(vals)} frames"
                         f"{' (UNSTEADY - widened to the whole stand)' if widened else ''}"
                         f" (fault at {med - VALGUS_SEP_DROP_MM:.0f} mm)")

    def _tilt_refresh(self):
        """The standing shoulder line, from the same trailing window as the knee gap."""
        if not self._tilt_buf:
            return
        t_end = self._tilt_buf[-1][0]
        win = [v for t, v in self._tilt_buf if t >= t_end - GAP_WINDOW_S]
        if len(win) < GAP_MIN_FRAMES:
            win = [v for _, v in self._tilt_buf]
        if len(win) < 3:
            return
        med = float(np.median(win))
        if abs(med) > 20.0:
            return
        self._tilt0 = med
        self.tilt_note = (f"standing shoulder tilt {med:+.1f} deg from "
                          f"{len(win)} frames (this is now zero)")

    def _tilt_ref(self) -> float:
        """The baseline to subtract, or zero when none was measured."""
        return self._tilt0 if np.isfinite(self._tilt0) else 0.0

    def _femur_refresh(self):
        """The athlete's thigh length, from the same trailing window as the knee gap."""
        if not self._femur_buf:
            return
        t_end = self._femur_buf[-1][0]
        win = [v for t, v in self._femur_buf if t >= t_end - GAP_WINDOW_S]
        if len(win) < GAP_MIN_FRAMES:
            win = [v for _, v in self._femur_buf]
        if len(win) < GAP_MIN_FRAMES:
            return
        med = float(np.median(win))
        if not (FEMUR_RANGE_MM[0] <= med <= FEMUR_RANGE_MM[1]):
            self.femur_note = f"femur {med:.0f} mm implausible - depth not scaled"
            return
        self._femur0 = med
        self.femur_note = (f"femur {med:.0f} mm "
                           f"(depth thresholds x{med / REF_FEMUR_MM:.2f})")

    def references_ready(self) -> bool:
        """True once the knee gap and femur references have been measured."""
        gap_ok = self._gap_supplied or (np.isfinite(self._gap0)
                                        and len(self._gap_buf) >= GAP_MIN_FRAMES)
        return bool(gap_ok and np.isfinite(self._femur0))

    def femur(self) -> float:
        """The femur the depth thresholds are scaled by, in mm, or NaN."""
        return self._femur0

    def set_baseline(self, theta0, h0, stance_kp=None, valgus0=None):
        """Supply the standing baseline from an external calibration step."""
        self._theta0, self._h0, self._calibrated = float(theta0), float(h0), True
        if valgus0 is not None and np.isfinite(valgus0):
            self._gap0 = float(valgus0)
            self._gap_supplied = True
        if stance_kp is not None:
            self._set_stance(stance_kp)

    def _set_stance(self, kp):
        """Measure and classify stance width from a standing pose."""
        self._stance_kp = np.asarray(kp, float)
        if not np.isfinite(self._femur0):
            fm = _femur_len(self._stance_kp)
            if np.isfinite(fm) and FEMUR_RANGE_MM[0] <= fm <= FEMUR_RANGE_MM[1]:
                self._femur0 = float(fm)
                self.femur_note = (f"femur {fm:.0f} mm from the calibration pose "
                                   f"(depth thresholds x{fm / REF_FEMUR_MM:.2f})")
        sw = M.stance_width_ratio(np.asarray(kp, float), self.frame,
                                  shoulder_mm=self.shoulder_mm)
        self.stance_width = sw
        _, self.stance_note = M.classify_stance_width(sw)

    def _reset_rep(self):
        """Clear the per-repetition accumulators."""
        self._t_S = None
        self._t_D = None
        self._t_A = None
        self._min_h = np.inf
        self._reached = False
        self._rise_ct = 0
        self._traj = []
        self._v_run = 0.0
        self._v_run_t0 = None
        self._v_run_n = 0
        self._v_best = 0.0
        self._v_best_n = 0
        self._v_best_t = np.nan
        self._v_peak = -np.inf
        self._v_peak_mm = -np.inf
        self._v_live_n = 0
        self._v_last_t = None

    def _velocity(self, h, t, pelvis_vel):
        """Pelvis vertical velocity in mm/s from the change in pelvis height."""
        if pelvis_vel is not None and np.isfinite(pelvis_vel):
            return float(pelvis_vel)
        if self._t_prev is None or not np.isfinite(h) or not np.isfinite(self._h_prev):
            v = 0.0
        else:
            dt = t - self._t_prev
            v = (h - self._h_prev) / dt if dt > 1e-6 else 0.0
        return v

    def _valid_frame(self, kp) -> bool:
        """True when every joint the measurements need is present and finite."""
        return bool(np.all(np.isfinite(kp[list(REQUIRED_JOINTS)])))

    def _track_valgus(self, n, t, dt_frame):
        """Update the sustained-cave run and return whether the live cue is on."""
        over = np.isfinite(n) and n > VALGUS_SEP_DROP_MM
        if np.isfinite(n) and n > self._v_peak:
            self._v_peak = n
        if over:
            if self._v_run <= 0.0:
                self._v_run_t0 = t
                self._v_run_n = 0
            self._v_run += dt_frame
            self._v_run_n += 1
            self._v_live_n += 1
            if self._v_run > self._v_best:
                self._v_best = self._v_run
                self._v_best_n = self._v_run_n
                self._v_best_t = self._v_run_t0
        else:
            self._v_run = 0.0
            self._v_run_n = 0
            self._v_live_n = 0
        return self._v_live_n >= VALGUS_LIVE_FRAMES

    def _valgus_limit_mm(self) -> float:
        """The fault line in the trace's own units."""
        return float(-VALGUS_SEP_DROP_MM)

    def _valgus_fraction(self, rep_s) -> float:
        """The longest unbroken cave as a share of the repetition."""
        if not (np.isfinite(rep_s) and rep_s > 0):
            return np.nan
        return float(self._v_best / rep_s)

    def _valgus_sustained(self, rep_s) -> bool:
        """True if the cave held for a large enough share of the repetition."""
        f = self._valgus_fraction(rep_s)
        return (np.isfinite(f) and f >= VALGUS_FAULT_FRACTION
                and self._v_best_n > VALGUS_LIVE_FRAMES)

    def update(self, kp, t, pelvis_vel=None) -> dict:
        """Advance the state machine by one frame and return the live state."""
        kp = np.asarray(kp, float)
        theta = M.knee_signal(kp)
        h = M.pelvis_height(kp, self.frame)
        dt_frame = (t - self._t_prev) if self._t_prev is not None else 0.0
        v = self._velocity(h, t, pelvis_vel)
        self._t_prev, self._h_prev = t, h

        abandoned = False
        if (self.phase != "SETUP" and self._t_good is not None
                and t - self._t_good > REP_ABANDON_S):
            self.abandoned_reps += 1
            self.phase = "SETUP"
            self._reset_rep()
            abandoned = True

        if not np.isfinite(theta) or not np.isfinite(h):
            return self._state(theta, h, v, None, rep_completed=False,
                               abandoned=abandoned)
        self._t_good = t

        if self._gap_supplied is False and self.rep_count == 0 and self.phase == "SETUP" \
                and theta > UPRIGHT_DEG and abs(v) < V_DEADBAND:
            self._gap_push(kp, t)

        live_cue = None
        if (self.phase in ("DESCENT", "BOTTOM", "ASCENT")
                and self._valid_frame(kp)
                and theta < FLEXION_GATE_DEG):
            gap = M.knee_separation(kp, self.frame)
            n = (self._gap0 - gap) if (np.isfinite(gap) and np.isfinite(self._gap0)) else np.nan
            self._valgus_mm = n
            if self._v_last_t is not None and t - self._v_last_t > VALGUS_MAX_GAP_S:
                self._v_run, self._v_run_n, self._v_live_n = 0.0, 0, 0
            self._v_last_t = t
            if np.isfinite(n) and n > self._v_peak_mm:
                self._v_peak_mm = n
            if self._track_valgus(n, t, dt_frame):
                live_cue = CUES["valgus"]
            t_rel = (t - self._t_S) if self._t_S is not None else 0.0
            self._traj.append((
                t_rel, h,
                M.depth_margin(kp, self.frame),
                M.knee_symmetry(kp),
                M.shoulder_tilt(kp, self.frame) - self._tilt_ref(),
                M.trunk_tibia_angle(kp, self.frame),
                self._valgus_mm,
                _signed_knee_diff(kp),
                theta,
            ))

        report = None
        rep_completed = False

        if self.phase == "SETUP":
            if not self._calibrated and abs(v) < V_DEADBAND:
                self._theta0 = theta if self._theta0 is None else 0.9 * self._theta0 + 0.1 * theta
                self._h0 = h if self._h0 is None else 0.9 * self._h0 + 0.1 * h
                self._base_n += 1
            ready = self._calibrated or self._base_n >= 3
            if ready and self._h0 is not None and h < self._h0 - H_DROP_ENTER and v < 0:
                self.phase = "DESCENT"
                self._t_S = t
                self._rise_ct = 0

        elif self.phase == "DESCENT":
            if h < self._min_h:
                self._min_h = h
            if theta < self._theta0 - MIN_KNEE_EXCURSION:
                self._reached = True
            settled = abs(h - self._min_h) < DWELL_BAND and abs(v) < V_DEADBAND
            self._rise_ct = self._rise_ct + 1 if v > V_RISE else 0
            if self._rise_ct >= RISE_FRAMES:
                self.phase = "ASCENT"
                self._t_A = t
            elif settled:
                self.phase = "BOTTOM"
                self._t_D = t

        elif self.phase == "BOTTOM":
            if h < self._min_h:
                self._min_h = h
            if theta < self._theta0 - MIN_KNEE_EXCURSION:
                self._reached = True
            self._rise_ct = self._rise_ct + 1 if v > V_RISE else 0
            if self._rise_ct >= RISE_FRAMES:
                self.phase = "ASCENT"
                self._t_A = t

        elif self.phase == "ASCENT":
            if abs(theta - self._theta0) < EPS_KNEE and abs(h - self._h0) < EPS_H:
                if self._reached:
                    self.rep_count += 1
                    report = self._assess(t)
                    rep_completed = True
                self.phase = "SETUP"
                self._reset_rep()

        return self._state(theta, h, v, live_cue, rep_completed, report,
                           abandoned=abandoned)

    def _bottom_median(self, col):
        """Median of one trajectory column over the bottom of the repetition."""
        hs = [row[1] for row in self._traj if np.isfinite(row[1])]
        if not hs:
            return np.nan
        h_min = min(hs)
        vals = [row[col] for row in self._traj
                if np.isfinite(row[1]) and abs(row[1] - h_min) < DWELL_BAND
                and np.isfinite(row[col])]
        return float(np.median(vals)) if vals else np.nan

    def _traj_mean(self, col):
        """Mean of one trajectory column over the flexed part of the repetition."""
        vals = [row[col] for row in self._traj if np.isfinite(row[col])]
        return float(np.mean(vals)) if vals else np.nan

    def _assess(self, t_end) -> RepReport:
        """Build the per-repetition report from the accumulated measurements."""
        margin = self._bottom_median(2)
        variation = classify_depth(margin, femur_mm=self._femur0)
        ttib = self._bottom_median(5)
        sym = self._traj_mean(3)

        sh_tilt = self._traj_mean(4)
        tilts = [abs(r[4]) for r in self._traj if np.isfinite(r[4])]
        sh_peak = max(tilts) if tilts else np.nan

        faults = []
        depth_met = None
        tgt, ach = DEPTH_ORDER.get(self.target), DEPTH_ORDER.get(variation)
        if tgt is None or ach is None:
            depth_met = None
            faults.append("depth_unmeasured")
        elif ach < tgt:
            depth_met = False
            faults.append("shallow")
        elif ach > tgt:
            depth_met = "deeper"
        else:
            depth_met = True

        rep_s = (t_end - self._t_S) if self._t_S is not None else np.nan
        t_desc_end = self._t_D if self._t_D is not None else self._t_A
        have_t = self._t_S is not None and self._t_A is not None
        valgus = self._valgus_sustained(rep_s)
        if valgus:
            faults.append("valgus")

        cues = []
        for name in faults:
            if name == "shallow":
                key = f"{self.target}_shallow"
                if key in DEPTH_CUES:
                    cues.append(DEPTH_CUES[key])
            elif name in CUES:
                cues.append(CUES[name])
        if depth_met == "deeper":
            key = f"{self.target}_deeper"
            if key in DEPTH_CUES:
                cues.append(DEPTH_CUES[key])
        if not faults and depth_met != "deeper":
            cues.append(CUES["good"])

        return RepReport(
            rep=self.rep_count,
            target_depth=self.target,
            variation=variation,
            depth_met=depth_met,
            depth_margin_mm=_r(margin),
            knee_at_depth=_r(self._bottom_median(8)),
            trunk_tibia_deg=_r(ttib),
            dominance=M.squat_dominance(ttib, DOMINANCE_CENTRE, DOMINANCE_BAND),
            t_bottom_s=_r(t_desc_end - self._t_S, 2) if have_t else np.nan,
            t_ascent_s=_r(self._t_A - self._t_S, 2) if have_t else np.nan,
            descent_s=_r(t_desc_end - self._t_S, 2) if have_t else np.nan,
            ascent_s=_r(t_end - self._t_A, 2) if have_t else np.nan,
            bottom_dwell_s=_r(self._t_A - t_desc_end, 2) if have_t else np.nan,
            valgus=bool(valgus),
            valgus_s=_r(self._v_best, 2),
            valgus_frac=_r(self._valgus_fraction(rep_s), 3),
            valgus_t=_r(self._v_best_t - self._t_S, 2)
                if (np.isfinite(self._v_best_t) and self._t_S is not None) else np.nan,
            valgus_peak=_r(self._v_peak, 3) if np.isfinite(self._v_peak) else np.nan,
            valgus_dev_mm=_r(self._v_peak_mm, 1) if np.isfinite(self._v_peak_mm) else np.nan,
            valgus_limit_mm=_r(self._valgus_limit_mm(), 1),
            knee_gap_mm=_r(self._gap0, 1) if np.isfinite(self._gap0) else np.nan,
            femur_mm=(_r(self._femur0) if np.isfinite(self._femur0) else None),
            depth_scale=_r(depth_scale(self._femur0), 6),
            depth_offset_mm=_r(DEPTH_OFFSET * depth_scale(self._femur0)),
            depth_band_mm=_r(PARALLEL_BAND * depth_scale(self._femur0)),
            depth_partial_max_mm=_r(PARTIAL_MAX_MM * depth_scale(self._femur0)),
            symmetry_deg=_r(sym),
            shoulder_tilt_deg=_r(sh_tilt),
            shoulder_peak_deg=_r(sh_peak),
            shoulder_tilt0_deg=(_r(self._tilt0) if np.isfinite(self._tilt0)
                                else None),
            shoulder_referenced=bool(np.isfinite(self._tilt0)),
            shoulder_band=shoulder_band(sh_tilt),
            shoulder_even_deg=SHOULDER_EVEN_DEG,
            shoulder_level=bool(shoulder_band(sh_tilt) == "even"),
            depth_traj=[[_r(r[0], 2), _r(r[2])] for r in self._traj if np.isfinite(r[2])],
            symmetry_traj=[[_r(r[0], 2), _r(r[3])] for r in self._traj if np.isfinite(r[3])],
            valgus_traj=[[_r(r[0], 2), _r(-r[6], 1)] for r in self._traj if np.isfinite(r[6])],
            sym_signed_traj=[[_r(r[0], 2), _r(r[7])] for r in self._traj if np.isfinite(r[7])],
            sym_signed_deg=_r(float(np.nanmean([r[7] for r in self._traj]))
                              if any(np.isfinite(r[7]) for r in self._traj) else np.nan),
            shoulder_tilt_traj=[[_r(r[0], 2), _r(r[4])] for r in self._traj if np.isfinite(r[4])],
            faults=faults,
            cues=cues,
        )

    def _state(self, theta, h, v, live_cue, rep_completed=False, report=None,
               abandoned=False):
        """Assemble the per-frame state dictionary."""
        return {
            "rep_abandoned": abandoned,
            "abandoned_reps": self.abandoned_reps,
            "refs_ready": self.references_ready(),
            "phase": self.phase,
            "rep_count": self.rep_count,
            "knee_angle": _r(theta) if np.isfinite(theta) else None,
            "depth_scale": _r(depth_scale(self._femur0), 6),
            "pelvis_h": _r(h) if np.isfinite(h) else None,
            "pelvis_v": _r(v),
            "live_cue": live_cue,
            "rep_completed": rep_completed,
            "last_rep": report.as_dict() if report is not None else None,
        }


def _r(x, nd=1):
    """Round to nd decimals, or NaN if not finite."""
    return round(float(x), nd) if (x is not None and np.isfinite(x)) else np.nan
