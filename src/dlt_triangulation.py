"""Direct Linear Transformation: triangulate one 3D point from several calibrated views."""

import json
import os
import numpy as np


def load_real_intrinsics():
    """Load the real camera matrix K you measured with the chessboard."""
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "..", "calib", "camera_intrinsics.json")
    if os.path.exists(path):
        with open(path) as f:
            data = json.load(f)
        K = np.array(data["camera_matrix_K"])
        rms = data.get("rms_reprojection_error_px")
        print(f"Loaded REAL intrinsics from calib/  (calibration RMS = {rms:.3f} px)")
        return K
    print("Real calib not found — using synthetic K.")
    return np.array([[900.0, 0, 960.0], [0, 900.0, 540.0], [0, 0, 1.0]])


def triangulate_point_dlt(projection_matrices, points_2d):
    """Triangulate ONE 3D point from N camera views."""
    n = len(projection_matrices)
    assert n == len(points_2d), "need one 2D point per projection matrix"
    assert n >= 2, "need at least two views to triangulate"

    A = []
    for P, (x, y) in zip(projection_matrices, points_2d):
        A.append(x * P[2, :] - P[0, :])
        A.append(y * P[2, :] - P[1, :])
    A = np.asarray(A)

    _, _, Vh = np.linalg.svd(A)
    X_hom = Vh[-1]

    X = X_hom[:3] / X_hom[3]
    return X


def make_projection_matrix(K, R, t):
    """P = K [R | t]."""
    Rt = np.hstack([R, t.reshape(3, 1)])
    return K @ Rt


def project(P, X):
    """Project a 3D point X (3,) through P (3x4) to pixel coords (2,)."""
    Xh = np.append(X, 1.0)
    x = P @ Xh
    return x[:2] / x[2]


def rotation_y(deg):
    """Rotation matrix about the Y axis, angle in degrees."""
    a = np.radians(deg)
    c, s = np.cos(a), np.sin(a)
    return np.array([[ c, 0, s],
                     [ 0, 1, 0],
                     [-s, 0, c]])


def run_sample_test():
    print("=" * 62)
    print("DLT triangulation — sample-data sanity test")
    print("=" * 62)

    K = load_real_intrinsics()

    R1 = np.eye(3)
    t1 = np.array([0.0, 0.0, 2.5])
    P1 = make_projection_matrix(K, R1, t1)

    R2 = rotation_y(30)
    t2 = np.array([-1.2, 0.0, 2.5])
    P2 = make_projection_matrix(K, R2, t2)

    X_true = np.array([0.15, -0.10, 0.40])
    print(f"\nGround-truth 3D point : {X_true}")

    x1 = project(P1, X_true)
    x2 = project(P2, X_true)
    print(f"Seen in camera 1 (px) : {x1.round(2)}")
    print(f"Seen in camera 2 (px) : {x2.round(2)}")

    X_est = triangulate_point_dlt([P1, P2], [x1, x2])
    err = np.linalg.norm(X_est - X_true)
    print("\n--- Perfect (noise-free) 2D points ---")
    print(f"Recovered 3D point    : {X_est.round(4)}")
    print(f"3D error vs truth     : {err*1000:.4f} mm  (should be ~0)")

    rng = np.random.default_rng(0)
    x1n = x1 + rng.normal(0, 1.0, 2)
    x2n = x2 + rng.normal(0, 1.0, 2)
    X_noisy = triangulate_point_dlt([P1, P2], [x1n, x2n])
    err_noisy = np.linalg.norm(X_noisy - X_true)
    print("\n--- With ~1 px of 2D detection noise ---")
    print(f"Recovered 3D point    : {X_noisy.round(4)}")
    print(f"3D error vs truth     : {err_noisy*1000:.2f} mm")

    re1 = np.linalg.norm(project(P1, X_noisy) - x1n)
    re2 = np.linalg.norm(project(P2, X_noisy) - x2n)
    print("\n--- Reprojection error of the noisy estimate ---")
    print(f"Camera 1 reprojection : {re1:.3f} px")
    print(f"Camera 2 reprojection : {re2:.3f} px")

    R3 = rotation_y(-25)
    t3 = np.array([1.1, 0.0, 2.5])
    P3 = make_projection_matrix(K, R3, t3)
    x3n = project(P3, X_true) + rng.normal(0, 1.0, 2)
    X_three = triangulate_point_dlt([P1, P2, P3], [x1n, x2n, x3n])
    err_three = np.linalg.norm(X_three - X_true)
    print("\n--- Same noise, but 3 cameras instead of 2 ---")
    print(f"Recovered 3D point    : {X_three.round(4)}")
    print(f"3D error vs truth     : {err_three*1000:.2f} mm  (usually < 2-cam)")

    print("\n" + "=" * 62)
    print("If the perfect case is ~0 mm and the noisy case is small,")
    print("your DLT is working correctly.")
    print("=" * 62)


if __name__ == "__main__":
    run_sample_test()
