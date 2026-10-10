"""Work out which checkerboard pattern you are holding, when capture reports no board."""

import sys
import time
import cv2
try:
    import viz
except Exception:
    pass

CANDIDATES = [(9, 6), (6, 9), (8, 6), (6, 8), (10, 7), (7, 10),
              (9, 7), (7, 9), (8, 5), (5, 8), (7, 5), (5, 7)]
FLAGS = cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE


def open_camera(index):
    cap = cv2.VideoCapture(index, cv2.CAP_AVFOUNDATION)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    for _ in range(45):
        ok, f = cap.read()
        if ok and f is not None and f.mean() > 5:
            return cap
        time.sleep(0.03)
    return cap


def main(index):
    cap = open_camera(index)
    print("Hold the board up, flat, whole board in view. Trying patterns...")
    last = None
    while True:
        ok, frame = cap.read()
        if not ok or frame is None:
            continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        hit = None
        for size in CANDIDATES:
            found, corners = cv2.findChessboardCorners(gray, size, FLAGS)
            if found:
                hit = (size, corners)
                break
        disp = frame.copy()
        if hit:
            size, corners = hit
            cv2.drawChessboardCorners(disp, size, corners, True)
            cv2.putText(disp, f"DETECTED (cols,rows) = {size}", (12, 34),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            if size != last:
                print(f"  detected pattern: {size}")
                last = size
        else:
            cv2.putText(disp, "no pattern matched - hold flat, whole board in frame",
                        (12, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        cv2.imshow("board check (q to quit)", disp)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break
    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    idx = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    main(idx)
