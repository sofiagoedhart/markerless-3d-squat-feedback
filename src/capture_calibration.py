"""Countdown auto-capture of synchronised checkerboard images for calibration."""

import os
import sys
import time
import glob
import cv2
import numpy as np

CHECKERBOARD = (8, 6)
COUNTDOWN_SEC = 5
EXTRINSIC_COUNTDOWN_SEC = 5
TARGET_INTRINSIC = 20
TARGET_EXTRINSIC = 30

STEADY_HINT_PX_PER_SEC = 25.0

REQUIRE_ALL = os.environ.get("REQUIRE_ALL", "1") == "1"
CAP_WIDTH, CAP_HEIGHT = 1280, 720

DISPLAY_WIDTH = 1800
EXTRINSIC_TILE = (640, 360)

FIND_FLAGS = (cv2.CALIB_CB_ADAPTIVE_THRESH |
              cv2.CALIB_CB_NORMALIZE_IMAGE)

_win_state = {}


def show(win, img, pos=None, width=None):
    """Show in a large, resizable, movable window."""
    if win not in _win_state:
        cv2.namedWindow(win, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)
        if pos is not None:
            try:
                cv2.moveWindow(win, pos[0], pos[1])
            except Exception:
                pass
        _win_state[win] = False
    cv2.imshow(win, img)
    if not _win_state[win]:
        h, w = img.shape[:2]
        ww = width if width else DISPLAY_WIDTH
        try:
            cv2.resizeWindow(win, ww, max(1, int(ww * h / w)))
        except Exception:
            pass
        _win_state[win] = True


def open_camera(index):
    cap = cv2.VideoCapture(index, cv2.CAP_AVFOUNDATION)
    if not cap.isOpened():
        return None
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAP_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAP_HEIGHT)
    try:
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    except Exception:
        pass
    for _ in range(45):
        ok, frame = cap.read()
        if ok and frame is not None and frame.mean() > 5:
            h, w = frame.shape[:2]
            if (w, h) != (CAP_WIDTH, CAP_HEIGHT):
                print(f"  cam{index} returned {w}x{h}, expected "
                      f"{CAP_WIDTH}x{CAP_HEIGHT} — intrinsics will NOT match.")
            return cap
        time.sleep(0.03)
    cap.release()
    return None


def grab_synced(caps):
    """Capture one frame per camera with minimal delay between cameras."""
    for cap in caps.values():
        cap.grab()
    frames = {}
    for i, cap in caps.items():
        ok, frame = cap.retrieve()
        if ok and frame is not None:
            frames[i] = frame
    return frames


def detect_board(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    found, corners = cv2.findChessboardCorners(gray, CHECKERBOARD, FIND_FLAGS)
    return found, corners


def board_shift(prev, cur):
    """Largest per-corner movement (px) between two {cam: corners} dicts."""
    shared = [i for i in cur if i in prev and cur[i] is not None and prev[i] is not None]
    if not shared:
        return float("inf")
    return max(float(np.abs(cur[i].reshape(-1, 2) - prev[i].reshape(-1, 2)).max())
               for i in shared)


def overlay(disp, lines, countdown=None, colour=(0, 255, 0)):
    y = 34
    for text in lines:
        cv2.putText(disp, text, (12, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, colour, 2)
        y += 30
    if countdown is not None:
        cv2.putText(disp, str(countdown), (disp.shape[1] // 2 - 20, disp.shape[0] // 2),
                    cv2.FONT_HERSHEY_SIMPLEX, 3.0, (0, 255, 255), 5)


def capture_intrinsic(index):
    outdir = f"calib_images/intrinsic/cam{index}"
    os.makedirs(outdir, exist_ok=True)
    cap = open_camera(index)
    if cap is None:
        print(f"Camera {index} did not open.")
        return
    win = f"Intrinsic capture - cam {index} (q to quit)"
    print(f"Camera {index}: move the board into varied poses; it auto-saves every "
          f"{COUNTDOWN_SEC}s when the board is detected. Target {TARGET_INTRINSIC}.")
    saved = 0
    next_cap = time.time() + COUNTDOWN_SEC
    while saved < TARGET_INTRINSIC:
        ok, frame = cap.read()
        if not ok or frame is None:
            continue
        found, corners = detect_board(frame)
        disp = frame.copy()
        if found:
            cv2.drawChessboardCorners(disp, CHECKERBOARD, corners, found)
        remaining = next_cap - time.time()
        status = "BOARD OK" if found else "no board - reposition"
        overlay(disp, [f"cam {index}   saved {saved}/{TARGET_INTRINSIC}", status],
                countdown=max(0, int(remaining) + 1),
                colour=(0, 255, 0) if found else (0, 0, 255))
        if remaining <= 0:
            if found:
                cv2.imwrite(f"{outdir}/img_{saved:02d}.png", frame)
                saved += 1
                print(f"  saved {saved}/{TARGET_INTRINSIC}\a")
            else:
                print("  (skipped — no board in view)")
            next_cap = time.time() + COUNTDOWN_SEC
        show(win, disp)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break
    cap.release()
    cv2.destroyAllWindows()
    print(f"Done cam {index}: {saved} images in {outdir}")


def clear_extrinsic_dirs(indices):
    """Delete old set_*.png before a new capture."""
    stale = []
    for i in indices:
        stale += glob.glob(f"calib_images/extrinsic/cam{i}/*.png")
    if not stale:
        return True
    print(f"\n{len(stale)} existing image(s) in calib_images/extrinsic/.")
    print("  calibrate_extrinsics.py reuses ALL images present, so old frames from")
    print("  previous camera positions would poison this calibration.")
    ans = input("  Delete them and start clean? [Y/n] ").strip().lower()
    if ans in ("", "y", "yes"):
        for p in stale:
            os.remove(p)
        print(f"  Deleted {len(stale)} old image(s).\n")
        return True
    print("  Keeping them — ONLY correct if the cameras have not moved since.\n")
    return False


def confirm_identity(caps):
    """Show one labelled frame per camera so the physical identity can be confirmed."""
    frames = grab_synced(caps)
    for k, i in enumerate(sorted(frames)):
        d = cv2.resize(frames[i].copy(), EXTRINSIC_TILE)
        cv2.putText(d, f"index {i}", (12, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 255), 3)
        pos = (20 + (k % 2) * (EXTRINSIC_TILE[0] + 30), 60 + (k // 2) * (EXTRINSIC_TILE[1] + 80))
        show(f"IDENTITY CHECK index {i}", d, pos=pos, width=EXTRINSIC_TILE[0])
    cv2.waitKey(600)
    print("\nIDENTITY CHECK — look at the three windows just opened.")
    print("  Expected: index 0 = LEFT camera, index 1 = CENTRE (reference), index 2 = RIGHT.")
    ans = input("  Does that match the physical rig? [Y/n] ").strip().lower()
    for i in sorted(frames):
        try:
            cv2.destroyWindow(f"IDENTITY CHECK index {i}")
        except Exception:
            pass
    if ans not in ("", "y", "yes"):
        print("\n  STOP. The indices are shuffled, so each camera would get the wrong")
        print("  intrinsics. Re-plug in the right order (or pass the indices in the")
        print("  order that makes 0=left, 1=centre, 2=right) and run this again.\n")
        return False
    return True


def capture_extrinsic(indices):
    caps = {}
    for i in indices:
        os.makedirs(f"calib_images/extrinsic/cam{i}", exist_ok=True)
        cap = open_camera(i)
        if cap is None:
            print(f"Camera {i} did not open — check ports/bandwidth.")
        else:
            caps[i] = cap
    if len(caps) < 2:
        print("Need at least 2 cameras open for extrinsics.")
        return
    if not confirm_identity(caps):
        for c in caps.values():
            c.release()
        cv2.destroyAllWindows()
        return
    clear_extrinsic_dirs(list(caps))
    need_txt = "ALL cameras" if REQUIRE_ALL else ">=2 cameras"
    print(f"Extrinsics: position the board so {need_txt} see it, hold it as steady as")
    print(f"you can, and a set saves every {EXTRINSIC_COUNTDOWN_SEC}s. Target {TARGET_EXTRINSIC} sets.")
    print("The cameras are latched within a few ms of each other (grab_synced), so")
    print("normal hand-held steadiness is fine — a stand is better if you have one.")
    print("The overlay shows board motion in px/s for INFORMATION ONLY - it never")
    print("blocks a save. Every countdown that sees the board writes a set.")
    saved = 0
    next_cap = time.time() + EXTRINSIC_COUNTDOWN_SEC
    prev_corners = None
    prev_t = None
    while saved < TARGET_EXTRINSIC:
        frames = grab_synced(caps)
        if not frames:
            continue
        founds, corners = {}, {}
        for i, frame in frames.items():
            founds[i], cor = detect_board(frame)
            corners[i] = cor if founds[i] else None

        now = time.time()
        if prev_corners and prev_t:
            dt = max(1e-3, now - prev_t)
            speed = board_shift(prev_corners, corners) / dt
        else:
            speed = float("inf")
        prev_corners = corners if any(v is not None for v in corners.values()) else None
        prev_t = now
        is_steady = speed <= STEADY_HINT_PX_PER_SEC

        remaining = next_cap - time.time()
        n_found = sum(1 for v in founds.values() if v)
        need = len(caps) if REQUIRE_ALL else 2

        if remaining <= 0:
            if n_found >= need:
                for i in frames:
                    cv2.imwrite(f"calib_images/extrinsic/cam{i}/set_{saved:02d}.png", frames[i])
                saved += 1
                seen = [i for i in founds if founds[i]]
                print(f"  set {saved}/{TARGET_EXTRINSIC} saved; board seen by cams {seen}\a")
                next_cap = time.time() + EXTRINSIC_COUNTDOWN_SEC
            else:
                seen = [i for i in founds if founds[i]]
                print(f"  (skipped - board must be visible to {need} cameras, "
                      f"saw {n_found} {seen}; move it into the shared volume)")
                next_cap = time.time() + EXTRINSIC_COUNTDOWN_SEC

        motion = ("steady" if is_steady else f"{speed:.0f} px/s") if speed < 1e5 else "--"
        status = (f"sets {saved}/{TARGET_EXTRINSIC}   next {max(0, int(remaining)+1)}s   "
                  f"need {need} OK   motion {motion}")
        tw, th = EXTRINSIC_TILE
        for k, i in enumerate(sorted(frames)):
            d = frames[i].copy()
            if founds[i]:
                _, cor = detect_board(d)
                cv2.drawChessboardCorners(d, CHECKERBOARD, cor, True)
            d = cv2.resize(d, EXTRINSIC_TILE)
            cv2.putText(d, f"cam{i} {'OK' if founds[i] else '--'}", (10, 34),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0,
                        (0, 255, 0) if founds[i] else (0, 0, 255), 2)
            cv2.putText(d, status, (10, d.shape[0] - 14),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
            pos = (20 + (k % 2) * (tw + 30), 60 + (k // 2) * (th + 80))
            show(f"extrinsic cam{i} (q quits)", d, pos=pos, width=tw)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break
    for cap in caps.values():
        cap.release()
    cv2.destroyAllWindows()
    print(f"Done: {saved} synchronized sets saved.")


if __name__ == "__main__":
    args = sys.argv[1:]
    if len(args) < 2 or args[0] not in ("intrinsic", "extrinsic"):
        print("Usage:")
        print("  python src/capture_calibration.py intrinsic 0")
        print("  python src/capture_calibration.py extrinsic 0 1 2")
        sys.exit(0)
    if args[0] == "intrinsic":
        capture_intrinsic(int(args[1]))
    else:
        capture_extrinsic([int(a) for a in args[1:]])
