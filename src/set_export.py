"""Write a set's per-repetition assessments to disk as the set closes."""
import json
import os
import sys
import time

import numpy as np

import rep_engine as RE


def _plain(x):
    """NumPy scalars and arrays as JSON-safe Python values."""
    if isinstance(x, (np.floating, np.integer)):
        x = x.item()
    if isinstance(x, float) and not np.isfinite(x):
        return None
    if isinstance(x, np.ndarray):
        return [_plain(v) for v in x.tolist()]
    if isinstance(x, dict):
        return {k: _plain(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_plain(v) for v in x]
    return x


def thresholds_in_force():
    """The assessment constants this run scored against, for reproducibility."""
    return {
        "depth_offset_mm": RE.DEPTH_OFFSET,
        "depth_band_mm": RE.PARALLEL_BAND,
        "depth_partial_max_mm": RE.PARTIAL_MAX_MM,
        "ref_femur_mm": RE.REF_FEMUR_MM,
        "valgus_sep_drop_mm": RE.VALGUS_SEP_DROP_MM,
        "valgus_fault_fraction": RE.VALGUS_FAULT_FRACTION,
        "shoulder_even_deg": RE.SHOULDER_EVEN_DEG,
        "min_knee_excursion_deg": RE.MIN_KNEE_EXCURSION,
        "dominance_centre_deg": RE.DOMINANCE_CENTRE,
        "dominance_band_deg": RE.DOMINANCE_BAND,
    }


def set_record(reports, *, session_id, set_index, target, label=None, engine=None,
               theta0_deg=None, h0_mm=None, calibration=None, driver="terminal",
               notes="", options=None):
    """One set as a JSON-safe dict: what was measured, and what it was measured against."""
    baselines = {"theta0_deg": theta0_deg, "h0_mm": h0_mm}
    if engine is not None:
        femur = getattr(engine, "femur", None)
        if callable(femur):
            femur = femur()
        baselines.update({
            "standing_knee_gap_mm": getattr(engine, "_gap0", None),
            "femur_mm": femur,
            "gap_note": getattr(engine, "gap_note", None),
            "femur_note": getattr(engine, "femur_note", None),
            "reps_abandoned": getattr(engine, "abandoned_reps", 0),
        })
    return _plain({
        "session_id": session_id,
        "set_index": set_index,
        "label": label,
        "target": target,
        "driver": driver,
        "written_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "notes": notes,
        "calibration": calibration,
        "baselines": baselines,
        "thresholds": thresholds_in_force(),
        "options": options,
        "argv": list(sys.argv),
        "reps_detected": len(reports),
        "reps": list(reports),
    })


def write_set(dirpath, reports, **kw):
    """Write one set's record and return its path, or None if there was nothing to write."""
    if not reports:
        return None
    os.makedirs(dirpath, exist_ok=True)
    rec = set_record(reports, **kw)
    stem = f"{rec['set_index']:02d}_{rec.get('label') or rec.get('target') or 'set'}"
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in stem)
    path = os.path.join(dirpath, safe + ".json")
    text = json.dumps(rec, indent=1)
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        fh.write(text)
    os.replace(tmp, path)
    return path
