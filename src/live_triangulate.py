"""Live 3D skeleton from three calibrated cameras, drawn back onto the camera views."""

import os
import sys
import json
import time
import numpy as np
import cv2
from ultralytics import YOLO

from multiview_triangulate import Camera, triangulate_skeleton, N_JOINTS
from dlt_triangulation import project
from kalman_smoother import SkeletonKalman

CAP_WIDTH, CAP_HEIGHT = 1280, 720
CONF_THRESH = 0.5
MIN_VIEWS = 2

EDGES = [(5, 7), (7, 9), (6, 8), (8, 10), (5, 6), (5, 11), (6, 12),
         (11, 12), (11, 13), (13, 15), (12, 14), (14, 16), (0, 5), (0, 6)]

DISPLAY_WIDTH = 720
_win = {}


def show(win, img, pos=None, width=DISPLAY_WIDTH):
    """One resizable, movable window per camera; resize/move applied AFTER the first imshow (macOS ignores them beforehand); KEEPRATIO stops stretching."""
    if win not in _win:
        cv2.namedWindow(win, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)
        if pos is not None:
            try:
                cv2.moveWindow(win, pos[0], pos[1])
            except Exception:
                pass
        _win[win] = False
    cv2.imshow(win, img)
    if not _win[win]:
        h, w = img.shape[:2]
        try:
            cv2.resizeWindow(win, width, max(1, int(width * h / w)))
        except Exception:
            pass
        _win[win] = True


def pick_device():
    try:
        import torch
        if torch.backends.mps.is_available():
            return "mps"
    except Exception:
        pass
    return "cpu"


def open_camera(index):
    cap = cv2.VideoCapture(index, cv2.CAP_AVFOUNDATION)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAP_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAP_HEIGHT)
    for _ in range(45):
        ok, f = cap.read()
        if ok and f is not None and f.mean() > 5:
            return cap
        time.sleep(0.03)
    return None


def _dist_for(i):
    """That camera's distortion coefficients from its intrinsics file."""
    path = os.path.join("calib", f"cam{i}_intrinsics.json")
    if not os.path.exists(path):
        print(f"  cam{i}: no {path} - triangulating WITHOUT lens-distortion "
              f"correction for this camera")
        return None
    return np.array(json.load(open(path))["dist_coeffs"], float).ravel()


def load_rig(indices):
    """Build a Camera per index from calib/extrinsics.json (K, R, t -> P)."""
    data = json.load(open("calib/extrinsics.json"))
    cams = data["cameras"]
    rig = []
    for i in indices:
        if str(i) not in cams:
            raise KeyError(f"cam{i} not in extrinsics.json (has {list(cams)}).")
        c = cams[str(i)]
        rig.append(Camera(np.array(c["K"]), np.array(c["R"]), np.array(c["t"]),
                          name=f"cam{i}", dist=_dist_for(i)))
    print(f"Loaded rig from calib/extrinsics.json (units: {data.get('units','mm')}).")
    return rig


def best_person(res):
    """Return (17,2) xy and (17,) conf for the highest-confidence person, or (None,None)."""
    kp = res.keypoints
    if kp is None or kp.xy is None or kp.xy.shape[0] == 0:
        return None, None
    if res.boxes is not None and res.boxes.conf is not None and len(res.boxes.conf) > 0:
        idx = int(res.boxes.conf.argmax())
    else:
        idx = 0
    xy = kp.xy[idx].cpu().numpy()
    conf = kp.conf[idx].cpu().numpy() if kp.conf is not None else np.ones(N_JOINTS)
    return xy, conf


def draw_reprojection(frame, P, joints3d, colour=(0, 255, 0)):
    """Reproject the 3D joints into this camera and draw them — the self-check."""
    pix = {}
    for j in range(N_JOINTS):
        if np.any(np.isnan(joints3d[j])):
            continue
        uv = project(P, joints3d[j])
        if np.all(np.isfinite(uv)):
            pix[j] = (int(uv[0]), int(uv[1]))
    for a, b in EDGES:
        if a in pix and b in pix:
            cv2.line(frame, pix[a], pix[b], colour, 2)
    for j, (u, v) in pix.items():
        cv2.circle(frame, (u, v), 4, colour, -1)
    return len(pix)


def dist(a, b):
    if np.any(np.isnan(a)) or np.any(np.isnan(b)):
        return None
    return float(np.linalg.norm(a - b))


def main(indices):
    rig = load_rig(indices)
    device = pick_device()
    print(f"Loading YOLO11n-pose on {device} ...")
    model = YOLO("yolo11n-pose.pt")
    caps = {}
    for i in indices:
        cap = open_camera(i)
        if cap is None:
            print(f"cam{i} did not open.")
        else:
            caps[i] = cap
    if len(caps) < 2:
        print("Need at least 2 cameras open.")
        return
    order = [i for i in indices if i in caps]
    kalman = SkeletonKalman(process_var=60.0, measurement_var=1e-4)

    prev = time.time()
    frame_count = 0
    print("Running... green skeleton = your 3D reprojected back in. Press q to quit.")
    while True:
        frames, valid = [], []
        for i in order:
            ok, f = caps[i].read()
            if ok and f is not None:
                frames.append(f)
                valid.append(i)
        if len(frames) < 2:
            continue

        results = model(frames, verbose=False, device=device)

        pts = np.full((len(rig), N_JOINTS, 2), np.nan)
        conf = np.zeros((len(rig), N_JOINTS))
        for k, i in enumerate(valid):
            xy, cf = best_person(results[k])
            if xy is not None:
                ri = indices.index(i)
                pts[ri] = xy
                conf[ri] = cf

        raw3d, nviews = triangulate_skeleton(rig, pts, conf,
                                             conf_thresh=CONF_THRESH, min_views=MIN_VIEWS)
        sm3d = kalman.update(raw3d, 1.0 / 30.0)

        n_rec = int(np.sum(~np.isnan(sm3d[:, 0])))
        now = time.time()
        fps = 1.0 / (now - prev) if now > prev else 0
        prev = now
        for k, i in enumerate(valid):
            disp = frames[k]
            ri = indices.index(i)
            draw_reprojection(disp, rig[ri].P, sm3d)
            cv2.putText(disp, f"cam{i}", (12, 42), cv2.FONT_HERSHEY_SIMPLEX, 1.3,
                        (0, 255, 0), 3)
            cv2.putText(disp, f"3D joints {n_rec}/{N_JOINTS}   FPS {fps:.1f}",
                        (12, disp.shape[0] - 18), cv2.FONT_HERSHEY_SIMPLEX, 0.9,
                        (0, 255, 255), 2)
            pos = (20 + (k % 2) * (DISPLAY_WIDTH + 30),
                   60 + (k // 2) * (int(DISPLAY_WIDTH * 9 / 16) + 80))
            show(f"cam{i}  green=reprojected 3D (q quits)", disp, pos=pos)

        frame_count += 1
        if frame_count % 30 == 0:
            sw = dist(sm3d[5], sm3d[6])
            ua = dist(sm3d[5], sm3d[7])
            th = dist(sm3d[11], sm3d[13])
            def mm(x):
                return f"{x:.0f}mm" if x is not None else "n/a"
            print(f"  3D joints {n_rec}/{N_JOINTS} | shoulders {mm(sw)}  "
                  f"upperarm {mm(ua)}  thigh {mm(th)}  (sanity: ~350-450 / ~250-330 / ~350-450)")

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    for cap in caps.values():
        cap.release()
    cv2.destroyAllWindows()
    print("Done.")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python src/live_triangulate.py 0 1 2   (same indices you calibrated)")
        sys.exit(0)
    main([int(a) for a in sys.argv[1:]])
