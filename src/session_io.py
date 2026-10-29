"""Record a 3D session to disk and load it back, optionally re-filtered."""
from __future__ import annotations
import json
import os
import numpy as np

import metrics as M


class SessionRecorder:
    def __init__(self, path, meta=None):
        self.path = str(path)
        self.meta = dict(meta or {})
        self._kp, self._t = [], []
        self._raw, self._pts, self._conf = [], [], []

    def add(self, kp, t, raw=None, pts=None, conf=None):
        """Record one frame."""
        if kp is None:
            kp = np.full((17, 3), np.nan)
        self._kp.append(np.asarray(kp, np.float32))
        self._t.append(float(t))
        self._raw.append(None if raw is None else np.asarray(raw, np.float32))
        self._pts.append(None if pts is None else np.asarray(pts, np.float32))
        self._conf.append(None if conf is None else np.asarray(conf, np.float32))

    def __len__(self):
        return len(self._t)

    def save(self):
        if not self._t:
            return None
        d = os.path.dirname(self.path)
        if d:
            os.makedirs(d, exist_ok=True)
        arrays = {"kp": np.asarray(self._kp, np.float32),
                  "t": np.asarray(self._t, np.float64),
                  "meta": json.dumps(self.meta)}
        for name, seq, fill in (("kp_raw", self._raw, np.nan),
                                ("pts2d", self._pts, np.nan),
                                ("conf", self._conf, 0.0)):
            arr = _stack(seq, fill)
            if arr is not None:
                arrays[name] = arr
        np.savez_compressed(self.path, **arrays)
        return self.path


def _stack(seq, fill=np.nan):
    """(T,...) float32 from a list that may contain None holes -> None if every entry is None."""
    shape = next((np.shape(x) for x in seq if x is not None), None)
    if shape is None:
        return None
    blank = np.full(shape, fill, np.float32)
    return np.asarray([blank if x is None else x for x in seq], np.float32)


def load_session(path):
    """-> ([(kp (17,3) float64 mm, t seconds), ...], meta dict)."""
    z = np.load(path, allow_pickle=False)
    kp, t = z["kp"].astype(float), z["t"].astype(float)
    meta = json.loads(str(z["meta"])) if "meta" in z else {}
    return list(zip(kp, t)), meta


def load_session_filtered(path, channel="stored", min_cutoff=1.0, beta=0.020,
                          process_var=12.0, measurement_var=4.0):
    """-> ([(kp (17,3) mm, t s), ...], meta), smoothed however you ask."""
    if channel == "stored":
        return load_session(path)

    z = np.load(path, allow_pickle=False)
    if "kp_raw" not in z:
        raise SystemExit(
            f"{path} has no kp_raw channel -- it was recorded before 30 Aug "
            f"2026, so only the already-filtered kp exists and channel="
            f"{channel!r} cannot be honoured.")
    raw = z["kp_raw"].astype(float)
    t = z["t"].astype(float)
    meta = json.loads(str(z["meta"])) if "meta" in z else {}

    if channel == "raw":
        return list(zip(raw, t)), meta

    if channel == "euro":
        from one_euro import SkeletonOneEuro
        f = SkeletonOneEuro(min_cutoff=min_cutoff, beta=beta)
    elif channel == "kalman":
        from kalman_smoother import SkeletonKalman
        f = SkeletonKalman(process_var=process_var,
                           measurement_var=measurement_var)
    else:
        raise SystemExit(f"unknown channel {channel!r}")

    dt0 = float(np.median(np.diff(t)))
    out = [f.update(raw[i], min(max(float(t[i] - t[i - 1]) if i else dt0, 1e-3), 1.0))
           for i in range(len(t))]
    return list(zip(out, t)), meta


def load_session_arrays(path):
    """Every channel a recording holds, as arrays -> dict with keys kp, kp_raw, pts2d, conf, t, meta."""
    z = np.load(path, allow_pickle=False)
    have = set(z.files)
    out = {k: (z[k].astype(float) if k in have else None)
           for k in ("kp", "kp_raw", "pts2d", "conf", "t")}
    out["meta"] = json.loads(str(z["meta"])) if "meta" in have else {}
    return out


def body_frame_from_meta(meta):
    """Rebuild the BodyFrame stored with a recording."""
    try:
        f = meta["body_frame"]
        return M.BodyFrame(up=np.asarray(f["up"], float),
                           lateral=np.asarray(f["lateral"], float),
                           forward=np.asarray(f["forward"], float))
    except (KeyError, TypeError):
        return None


def meta_from_body_frame(frame: M.BodyFrame) -> dict:
    return {"up": [float(x) for x in frame.up],
            "lateral": [float(x) for x in frame.lateral],
            "forward": [float(x) for x in frame.forward]}
