"""Speed-adaptive low-pass smoothing; the default filter, because it cannot overshoot."""

import numpy as np

DT_MIN_S = 0.001
DT_MAX_S = 1.0


def _clamp_dt(dt):
    """The measured interval, bounded to [1, 1000] ms."""
    if dt is None or not np.isfinite(dt):
        return DT_MAX_S
    return float(min(max(float(dt), DT_MIN_S), DT_MAX_S))


def _alpha(cutoff_hz, dt):
    """First-order low-pass smoothing factor for a given cutoff and timestep."""
    tau = 1.0 / (2.0 * np.pi * cutoff_hz)
    return 1.0 / (1.0 + tau / dt)


class OneEuro:
    """One Euro filter for a single scalar channel."""

    def __init__(self, min_cutoff=1.0, beta=0.007, d_cutoff=1.0):
        self.min_cutoff = float(min_cutoff)
        self.beta = float(beta)
        self.d_cutoff = float(d_cutoff)
        self.x_prev = None
        self.dx_prev = 0.0

    def reset(self):
        self.x_prev = None
        self.dx_prev = 0.0

    def update(self, x, dt):
        if x is None or not np.isfinite(x):
            return None
        dt = _clamp_dt(dt)
        if self.x_prev is None:
            self.x_prev = float(x)
            self.dx_prev = 0.0
            return self.x_prev

        dx = (x - self.x_prev) / dt
        a_d = _alpha(self.d_cutoff, dt)
        dx_hat = a_d * dx + (1.0 - a_d) * self.dx_prev

        cutoff = self.min_cutoff + self.beta * abs(dx_hat)
        a = _alpha(cutoff, dt)

        x_hat = a * x + (1.0 - a) * self.x_prev

        self.x_prev = x_hat
        self.dx_prev = dx_hat
        return x_hat


class SkeletonOneEuro:
    """One OneEuro per axis per joint; same interface as SkeletonKalman."""

    def __init__(self, min_cutoff=1.0, beta=0.007, d_cutoff=1.0, n_joints=17,
                 max_coast=2):
        self.f = [[OneEuro(min_cutoff, beta, d_cutoff) for _ in range(3)]
                  for _ in range(n_joints)]
        self.n = n_joints
        self.max_coast = int(max_coast)
        self.misses = np.zeros(n_joints, dtype=int)

    def update(self, joints_3d, dt):
        j = np.asarray(joints_3d, dtype=float)
        out = np.full((self.n, 3), np.nan)
        for i in range(self.n):
            if np.any(~np.isfinite(j[i])):
                self.misses[i] += 1
                if self.misses[i] <= self.max_coast and self.f[i][0].x_prev is not None:
                    out[i] = [self.f[i][k].x_prev for k in range(3)]
                else:
                    for k in range(3):
                        self.f[i][k].reset()
                continue
            self.misses[i] = 0
            for k in range(3):
                out[i, k] = self.f[i][k].update(j[i, k], dt)
        return out
