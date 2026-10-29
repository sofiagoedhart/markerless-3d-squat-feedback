"""Triangulate a whole 17-joint skeleton from three views, gating on keypoint confidence."""

import numpy as np

from dlt_triangulation import (
    triangulate_point_dlt,
    make_projection_matrix,
    project,
)

COCO_KEYPOINTS = [
    "nose", "left_eye", "right_eye", "left_ear", "right_ear",
    "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "left_hip", "right_hip",
    "left_knee", "right_knee", "left_ankle", "right_ankle",
]
N_JOINTS = len(COCO_KEYPOINTS)


class Camera:
    """One calibrated camera in the rig: intrinsics K, extrinsics R and t, and optional lens-distortion coefficients."""

    def __init__(self, K, R, t, name="", dist=None):
        self.K = np.asarray(K, dtype=float)
        self.R = np.asarray(R, dtype=float)
        self.t = np.asarray(t, dtype=float).reshape(3)
        self.name = name
        self.dist = (None if dist is None
                     else np.asarray(dist, dtype=float).ravel())
        if self.dist is not None and not np.any(np.abs(self.dist) > 1e-12):
            self.dist = None
        self.P = make_projection_matrix(self.K, self.R, self.t)


def build_rig(cameras_krt):
    """Turn a list of (K, R, t[, name]) tuples into a list of Camera objects."""
    rig = []
    for i, spec in enumerate(cameras_krt):
        K, R, t = spec[0], spec[1], spec[2]
        name = spec[3] if len(spec) > 3 else f"cam{i}"
        rig.append(Camera(K, R, t, name))
    return rig


def triangulate_joint(rig, points_2d, confidences, conf_thresh=0.5, min_views=2):
    """Triangulate one joint from the cameras whose confidence passes the threshold."""
    good = []
    for i, (pt, c) in enumerate(zip(points_2d, confidences)):
        if pt is None or c < conf_thresh:
            continue
        pt = np.asarray(pt, dtype=float)
        if not np.all(np.isfinite(pt)):
            continue
        good.append(i)

    if len(good) < max(2, min_views):
        return None, []

    Ps = [rig[i].P for i in good]
    pts = [np.asarray(points_2d[i], dtype=float) for i in good]
    return triangulate_point_dlt(Ps, pts), good


def undistort_view(pts, cam):
    """Detector pixels -> ideal pinhole pixels for one camera."""
    if cam.dist is None:
        return pts
    import cv2
    pts = np.asarray(pts, dtype=float)
    out = pts.copy()
    ok = np.all(np.isfinite(pts), axis=-1)
    if not np.any(ok):
        return out
    q = pts[ok].reshape(-1, 1, 2)
    out[ok] = cv2.undistortPoints(q, cam.K, cam.dist, P=cam.K).reshape(-1, 2)
    return out


def triangulate_skeleton(rig, points_2d, confidences,
                         conf_thresh=0.5, min_views=2, undistort=True):
    """Triangulate all 17 joints for one frame from `points_2d`, shape (n_cam, 17, 2) in pixels, with matching (n_cam, 17) confidences."""
    points_2d = np.asarray(points_2d, dtype=float)
    if undistort:
        points_2d = np.stack([undistort_view(points_2d[c], rig[c])
                              for c in range(len(rig))])
    confidences = np.asarray(confidences, dtype=float)
    n_cam = len(rig)

    joints_3d = np.full((N_JOINTS, 3), np.nan)
    n_views = np.zeros(N_JOINTS, dtype=int)

    for j in range(N_JOINTS):
        pts_j = [points_2d[c, j] for c in range(n_cam)]
        conf_j = [confidences[c, j] for c in range(n_cam)]
        X, used = triangulate_joint(
            rig, pts_j, conf_j,
            conf_thresh=conf_thresh, min_views=min_views,
        )
        if X is not None:
            joints_3d[j] = X
            n_views[j] = len(used)
    return joints_3d, n_views


def _look_at_camera(position, target, K, up=(0, 1, 0), name=""):
    """Build a Camera that sits at `position` (world coords) and looks at `target`."""
    position = np.asarray(position, float)
    target = np.asarray(target, float)
    up = np.asarray(up, float)

    z = target - position
    z = z / np.linalg.norm(z)
    x = np.cross(up, z)
    x = x / np.linalg.norm(x)
    y = np.cross(z, x)
    R = np.vstack([x, y, z])
    t = -R @ position
    return Camera(K, R, t, name)


def _self_test():
    print("=" * 64)
    print("multiview_triangulate — synthetic 3-camera rig self-test")
    print("=" * 64)

    K = np.array([[1490.0, 0, 960.0],
                  [0, 1490.0, 540.0],
                  [0, 0, 1.0]])

    target = np.array([0.0, 0.9, 0.0])
    rig = [
        _look_at_camera([-1.6, 1.2, 2.4], target, K, name="cam_left"),
        _look_at_camera([0.0, 1.3, 2.9], target, K, name="cam_centre"),
        _look_at_camera([1.6, 1.2, 2.4], target, K, name="cam_right"),
    ]

    rng = np.random.default_rng(1)
    true_joints = np.array([
        [0.00, 1.65, 0.00],
        [-0.03, 1.68, 0.02], [0.03, 1.68, 0.02],
        [-0.07, 1.66, 0.00], [0.07, 1.66, 0.00],
        [-0.18, 1.45, 0.00], [0.18, 1.45, 0.00],
        [-0.24, 1.20, 0.03], [0.24, 1.20, 0.03],
        [-0.26, 0.95, 0.06], [0.26, 0.95, 0.06],
        [-0.12, 0.95, 0.00], [0.12, 0.95, 0.00],
        [-0.13, 0.52, 0.02], [0.13, 0.52, 0.02],
        [-0.13, 0.08, 0.04], [0.13, 0.08, 0.04],
    ])

    n_cam = len(rig)
    pts = np.full((n_cam, N_JOINTS, 2), np.nan)
    conf = np.full((n_cam, N_JOINTS), 0.9)
    for c in range(n_cam):
        for j in range(N_JOINTS):
            pts[c, j] = project(rig[c].P, true_joints[j]) + rng.normal(0, 1.0, 2)
    conf[0, 9] = conf[0, 10] = 0.05
    conf[2, 16] = 0.05

    est, nviews = triangulate_skeleton(rig, pts, conf)

    print(f"\n{'joint':<16}{'views':>6}{'3D error (mm)':>16}")
    print("-" * 40)
    errs = []
    for j, name in enumerate(COCO_KEYPOINTS):
        if np.any(np.isnan(est[j])):
            print(f"{name:<16}{nviews[j]:>6}{'MISSING':>16}")
            continue
        e = np.linalg.norm(est[j] - true_joints[j]) * 1000
        errs.append(e)
        print(f"{name:<16}{nviews[j]:>6}{e:>16.2f}")

    print("-" * 40)
    print(f"mean 3D error over reconstructed joints : {np.mean(errs):.2f} mm")
    print(f"joints reconstructed                    : {len(errs)}/{N_JOINTS}")
    print("\nNote: the confidence-gated joints (wrists on cam_left, one ankle")
    print("on cam_right) still reconstruct from the remaining cameras.")


if __name__ == "__main__":
    _self_test()
