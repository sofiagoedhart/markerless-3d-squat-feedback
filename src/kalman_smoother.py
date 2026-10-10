"""Constant-velocity Kalman smoothing of triangulated joints, kept for comparison; one_euro.py is the default."""

import numpy as np

N_JOINTS = 17


class JointKalman:
    """Constant-velocity Kalman filter for one 3D point."""

    def __init__(self, process_var=8.0, measurement_var=1e-4, max_coast=6):
        self.q = float(process_var)
        self.r = float(measurement_var)
        self.max_coast = int(max_coast)
        self.misses = 0
        self.x = None
        self.P = None
        self.H = np.zeros((3, 6))
        self.H[0, 0] = self.H[1, 1] = self.H[2, 2] = 1.0
        self.R = np.eye(3) * self.r

    def _F(self, dt):
        """State-transition: x += v*dt (constant velocity)."""
        F = np.eye(6)
        F[0, 3] = F[1, 4] = F[2, 5] = dt
        return F

    def _Q(self, dt):
        """Process-noise covariance for a constant-velocity model (white accel)."""
        q = self.q
        dt2, dt3, dt4 = dt * dt, dt ** 3, dt ** 4
        Q = np.zeros((6, 6))
        for i in range(3):
            Q[i, i] = dt4 / 4.0
            Q[i, i + 3] = Q[i + 3, i] = dt3 / 2.0
            Q[i + 3, i + 3] = dt2
        return Q * q

    def update(self, measurement, dt=1.0 / 30.0):
        """Advance one frame."""
        if self.x is None:
            if measurement is None or not np.all(np.isfinite(measurement)):
                return None
            self.x = np.array([*measurement, 0.0, 0.0, 0.0], dtype=float)
            self.P = np.eye(6)
            self.P[3:, 3:] *= 10.0
            self.misses = 0
            return self.x[:3].copy()

        F = self._F(dt)
        self.x = F @ self.x
        self.P = F @ self.P @ F.T + self._Q(dt)

        if measurement is not None and np.all(np.isfinite(measurement)):
            self.misses = 0
            z = np.asarray(measurement, dtype=float)
            y = z - self.H @ self.x
            S = self.H @ self.P @ self.H.T + self.R
            Kk = self.P @ self.H.T @ np.linalg.inv(S)
            self.x = self.x + Kk @ y
            self.P = (np.eye(6) - Kk @ self.H) @ self.P
        else:
            self.misses += 1
            if self.misses > self.max_coast:
                self.x = None
                self.P = None
                return None

        return self.x[:3].copy()


class SkeletonKalman:
    """One JointKalman per COCO joint; smooths a whole (17,3) skeleton stream."""

    def __init__(self, process_var=8.0, measurement_var=1e-4, n_joints=N_JOINTS):
        self.filters = [JointKalman(process_var, measurement_var)
                        for _ in range(n_joints)]
        self.n = n_joints

    def update(self, joints_3d, dt=1.0 / 30.0):
        """Smooth one frame: `joints_3d` is a (17, 3) array from triangulate_skeleton with NaN rows for missing joints."""
        joints_3d = np.asarray(joints_3d, dtype=float)
        out = np.full((self.n, 3), np.nan)
        for j in range(self.n):
            meas = joints_3d[j]
            meas = None if np.any(np.isnan(meas)) else meas
            sm = self.filters[j].update(meas, dt)
            if sm is not None:
                out[j] = sm
        return out


def _self_test():
    print("=" * 60)
    print("kalman_smoother — one-joint smoothing self-test")
    print("=" * 60)

    rng = np.random.default_rng(0)
    fps = 30.0
    dt = 1.0 / fps
    T = 150

    ts = np.arange(T) * dt
    truth = np.stack([
        0.30 + 0.02 * np.sin(2 * np.pi * 0.2 * ts),
        0.95 + 0.25 * np.sin(2 * np.pi * 0.5 * ts),
        0.05 + 0.01 * ts,
    ], axis=1)

    meas = truth + rng.normal(0, 0.004, truth.shape)
    dropout = np.zeros(T, dtype=bool)
    dropout[70:76] = True

    kf = JointKalman(process_var=8.0, measurement_var=1.6e-5)
    smoothed = np.full_like(truth, np.nan)
    for i in range(T):
        m = None if dropout[i] else meas[i]
        s = kf.update(m, dt)
        if s is not None:
            smoothed[i] = s

    raw_err = np.linalg.norm(meas - truth, axis=1) * 1000
    sm_err = np.linalg.norm(smoothed - truth, axis=1) * 1000

    keep = ~dropout
    print(f"\nframes                : {T}  @ {fps:.0f} fps")
    print(f"injected 3D noise     : ~4.0 mm per axis")
    print(f"raw    mean 3D error  : {np.mean(raw_err[keep]):.2f} mm")
    print(f"smooth mean 3D error  : {np.mean(sm_err[keep]):.2f} mm")
    print(f"noise reduction       : "
          f"{100 * (1 - np.mean(sm_err[keep]) / np.mean(raw_err[keep])):.0f}%")
    print(f"\nDuring the 6-frame dropout (frames 70-75) there is NO measurement,")
    print(f"so the filter coasts on predicted velocity and keeps outputting a")
    print(f"position (max error there {np.nanmax(sm_err[70:76]):.1f} mm) — the")
    print(f"point is there is no gap/hole in the 3D stream for Unity to trip on.")
    print("\nTune process_var UP for snappier tracking, DOWN for more smoothing.")


if __name__ == "__main__":
    _self_test()
