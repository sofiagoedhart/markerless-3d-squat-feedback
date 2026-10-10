"""Record each camera's raw video alongside a captured set."""
from __future__ import annotations
import os
import queue
import threading

import numpy as np
import cv2

FOURCC = cv2.VideoWriter_fourcc(*"MJPG")


class SetVideoWriter:
    """One .avi per camera for one set."""

    _open = set()

    def __init__(self, dir_, stem, cam_ids, fps=10.0, queue_max=24):
        self.dir, self.stem, self.fps = str(dir_), str(stem), float(fps)
        self.cam_ids = list(cam_ids)
        self._q = {i: queue.Queue(maxsize=int(queue_max)) for i in self.cam_ids}
        self._threads = {}
        self._times = {i: [] for i in self.cam_ids}
        self._written = {i: 0 for i in self.cam_ids}
        self._dropped = 0
        os.makedirs(self.dir, exist_ok=True)
        for i in self.cam_ids:
            th = threading.Thread(target=self._run, args=(i,), daemon=True)
            th.start()
            self._threads[i] = th
        SetVideoWriter._open.add(self)

    def path(self, cam):
        return os.path.join(self.dir, f"{self.stem}_cam{cam}.avi")

    def _run(self, cam):
        """Consumer thread: opens the writer lazily so the frame size comes from the real frames rather than an assumption."""
        w = None
        while True:
            item = self._q[cam].get()
            if item is None:
                break
            img, t = item
            if w is None:
                h, wd = img.shape[:2]
                w = cv2.VideoWriter(self.path(cam), FOURCC, self.fps, (wd, h))
                if not w.isOpened():
                    print(f"!! video disabled for cam{cam} (writer would not open)")
                    w = None
                    while self._q[cam].get() is not None:
                        pass
                    return
            try:
                w.write(img)
                self._written[cam] += 1
                self._times[cam].append(t)
            except Exception as exc:
                print(f"!! video write failed on cam{cam}: {exc}")
                break
        if w is not None:
            w.release()

    def add(self, frames, valid, t):
        """Queue one frame per valid camera."""
        for k, i in enumerate(valid):
            q = self._q.get(i)
            if q is None or frames is None or k >= len(frames):
                continue
            try:
                q.put_nowait((frames[k].copy(), float(t)))
            except queue.Full:
                self._dropped += 1

    def close(self):
        for i in self.cam_ids:
            try:
                self._q[i].put(None, timeout=5.0)
            except queue.Full:
                pass
        for th in self._threads.values():
            th.join(timeout=30.0)
        try:
            np.savez_compressed(
                os.path.join(self.dir, f"{self.stem}_frametimes.npz"),
                **{f"cam{i}": np.asarray(self._times[i], np.float64)
                   for i in self.cam_ids})
        except Exception as exc:
            print(f"!! could not save frame times: {exc}")
        SetVideoWriter._open.discard(self)
        return {"written": min(self._written.values()) if self._written else 0,
                "per_cam": {str(i): self._written[i] for i in self.cam_ids},
                "dropped": self._dropped,
                "files": [os.path.basename(self.path(i)) for i in self.cam_ids]}

    @classmethod
    def close_all(cls):
        """Finalise anything still open -- an unreleased AVI has no index and may not play back."""
        for v in list(cls._open):
            try:
                v.close()
            except Exception:
                pass


if __name__ == "__main__":
    import tempfile
    d = tempfile.mkdtemp()
    vid = SetVideoWriter(d, "selftest", [0, 1], fps=10.0)
    rng = np.random.default_rng(0)
    for n in range(20):
        f = [rng.integers(0, 255, (72, 128, 3), dtype=np.uint8) for _ in range(2)]
        vid.add(f, [0, 1], 1000.0 + n * 0.1)
    st = vid.close()
    cap = cv2.VideoCapture(os.path.join(d, "selftest_cam0.avi"))
    got = 0
    while cap.read()[0]:
        got += 1
    cap.release()
    z = np.load(os.path.join(d, "selftest_frametimes.npz"))
    assert st["written"] == 20, st
    assert got == 20, got
    assert z["cam0"].shape == (20,) and abs(z["cam0"][0] - 1000.0) < 1e-6
    print(f"OK -- {got} frames read back, times {z['cam0'][0]:.1f}..{z['cam0'][-1]:.1f}, "
          f"{st['dropped']} dropped")
