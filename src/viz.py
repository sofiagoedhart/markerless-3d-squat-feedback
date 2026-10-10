"""Make every OpenCV window large and resizable."""
import cv2

INIT_WIDTH = 1600
_seen = set()
_orig_imshow = cv2.imshow
_orig_named = cv2.namedWindow


def _named(winname, flags=None):
    _orig_named(winname, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)


def _imshow(winname, mat):
    first = winname not in _seen
    if first:
        _orig_named(winname, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)
        _seen.add(winname)
    _orig_imshow(winname, mat)
    if first:
        try:
            h, w = mat.shape[:2]
            cv2.resizeWindow(winname, INIT_WIDTH, max(1, int(INIT_WIDTH * h / w)))
        except Exception:
            pass


cv2.namedWindow = _named
cv2.imshow = _imshow
