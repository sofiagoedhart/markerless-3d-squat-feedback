"""Drive the whole downstream pipeline from a recording, with no cameras."""
from __future__ import annotations
import argparse
import time
import numpy as np

import metrics as M
from rep_engine import SquatRepEngine
from pose_to_unity import PoseStreamer, limb_lengths
from session_io import load_session, body_frame_from_meta
from control_listener import ControlListener


def build(frames, meta=None, calib_frames=25, target="parallel"):
    """-> (body frame, rep engine, floor origin, subject ankle-shoulder mm)."""
    JOINTS = (M.L_SHO, M.R_SHO, M.L_HIP, M.R_HIP,
              M.L_KNE, M.R_KNE, M.L_ANK, M.R_ANK)

    limit = max(calib_frames * 8, 200)
    clean, last = [], 0
    for i, (kp, _) in enumerate(frames[:limit]):
        if all(np.all(np.isfinite(kp[j])) for j in JOINTS):
            clean.append(kp)
            last = i
            if len(clean) >= calib_frames:
                break
    if not clean:
        raise SystemExit(
            f"no complete skeleton in the first {limit} frames — cannot "
            f"calibrate a standing baseline from this recording")
    stand = [kp for kp, _ in frames[:last + 1] if np.isfinite(kp).any()]
    frame = body_frame_from_meta(meta or {}) or M.calibrate_body_frame(stand)
    theta0 = (meta or {}).get("theta0_deg")
    h0 = (meta or {}).get("h0_mm")
    if theta0 is None or h0 is None:
        theta0 = float(np.nanmean([M.knee_signal(s) for s in clean]))
        h0 = float(np.nanmean([M.pelvis_height(s, frame) for s in clean]))
    else:
        theta0, h0 = float(theta0), float(h0)
    shoulder = PoseStreamer.subject_shoulder_width(clean, frame)
    eng = SquatRepEngine(frame, target=target, theta0=theta0, h0=h0,
                         stance_kp=clean[-1], shoulder_mm=shoulder)
    return (frame, eng, PoseStreamer.floor_origin(clean, frame),
            PoseStreamer.subject_hip_ankle(clean),
            PoseStreamer.subject_shoulder_width(clean, frame),
            limb_lengths(clean))


def refilter(path, frames, a):
    """Rebuild the frame list from the recording's PRE-smoothing channel."""
    from session_io import load_session_filtered
    return load_session_filtered(
        path, a.channel,
        min_cutoff=getattr(a, "euro_min_cutoff", 1.0),
        beta=getattr(a, "euro_beta", 0.020),
        process_var=getattr(a, "process_var", 12.0),
        measurement_var=getattr(a, "measurement_var", 4.0))[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", help="recorded .npz session (default: synthetic)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5006)
    ap.add_argument("--target", default="parallel", choices=["partial", "parallel", "deep"])
    ap.add_argument("--speed", type=float, default=1.0, help="playback rate multiplier")
    ap.add_argument("--once", action="store_true", help="play once instead of looping")
    ap.add_argument("--no-send", action="store_true", help="do not open a UDP socket")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--control-port", type=int, default=5007,
                    help="listen here for target/rep changes sent from Unity's settings page")
    ap.add_argument("--no-control", action="store_true")
    ap.add_argument("--no-mirror", action="store_true",
                    help="show true anatomy instead of the default gym-mirror view")
    ap.add_argument("--reps", nargs="+", default=["partial", "parallel", "deep"],
                    choices=["partial", "parallel", "deep"],
                    help="which reps the synthetic session contains, in order. "
                         "`--reps parallel` gives the single-rep demo.")
    ap.add_argument("--free-run", action="store_true",
                    help="play immediately instead of waiting for Start in Unity")
    ap.add_argument("--channel", default="stored",
                    choices=["stored", "raw", "euro", "kalman"],
                    help="3D stream to replay: as recorded, raw, or re-filtered with 'euro' or 'kalman'")
    ap.add_argument("--euro-min-cutoff", type=float, default=1.0)
    ap.add_argument("--euro-beta", type=float, default=0.020)
    ap.add_argument("--display-min-cutoff", type=float, default=0.5,
                    help="One Euro cutoff for the avatar stream only, applied to "
                         "kp_raw independently of --channel")
    ap.add_argument("--display-beta", type=float, default=0.002)
    ap.add_argument("--no-display-filter", action="store_true",
                    help="drive the avatar from the same stream the engine "
                         "sees, instead of a separately smoothed one")
    ap.add_argument("--process-var", type=float, default=12.0)
    ap.add_argument("--measurement-var", type=float, default=4.0)
    a = ap.parse_args()

    disp = None
    if a.file:
        frames, meta = load_session(a.file)
        if a.channel != "stored":
            frames = refilter(a.file, frames, a)
        if not a.no_display_filter:
            try:
                d = argparse.Namespace(channel="euro",
                                       euro_min_cutoff=a.display_min_cutoff,
                                       euro_beta=a.display_beta)
                disp = [kp for kp, _ in refilter(a.file, frames, d)]
                print(f"Avatar smoothing: One Euro ({a.display_min_cutoff}, "
                      f"{a.display_beta}) — display only.")
            except SystemExit:
                disp = None
        print(f"Replaying {a.file}: {len(frames)} frames, "
              f"{frames[-1][1]-frames[0][1]:.1f} s, channel={a.channel}")
    else:
        from synthetic_squat import make_session
        frames, meta = make_session(reps=tuple(a.reps)), {}
        print(f"Synthetic session: {len(frames)} frames, {' + '.join(a.reps)} "
              f"({frames[-1][1]:.0f} s). Feet start too wide and come in to "
              f"shoulder width; the left knee caves on the parallel rep and the "
              f"left shoulder rises on the deep one.")

    ctl = None if a.no_control else ControlListener(port=a.control_port, target=a.target).start()
    frame, eng, origin, subject_mm, shoulder_mm, limb_mm = build(frames, meta, target=a.target)
    stream = None if a.no_send else PoseStreamer(frame, a.host, a.port,
                                                 origin=origin, target=a.target,
                                                 subject_mm=subject_mm,
                                                 shoulder_mm=shoulder_mm,
                                                 mirror=not a.no_mirror,
                                                 limb_mm=limb_mm)
    if subject_mm:
        print(f"Subject hip-to-ankle: {subject_mm:.0f} mm "
              f"(the renderer scales the avatar to this, once).")
    if stream:
        print(f"Streaming to {a.host}:{a.port} — start Play in Unity.")
    print(f"Target depth: {a.target}.  Ctrl-C to stop.\n")

    t0_data = frames[0][1]
    wait_for_start = not a.free_run and ctl is not None
    if wait_for_start:
        print("Waiting for Start on the Unity setup screen "
              "(run with --free-run to skip).")
    loop = 0
    try:
        while True:
            eng2 = eng if loop == 0 else build(frames, meta, target=a.target)[1]
            if stream:
                stream.session = loop
                stream._trace = []

            def apply_settings():
                """Settings chosen in Unity take effect in the ENGINE, so the target the screen shows is always the target being scored."""
                if ctl is not None and ctl.take():
                    eng2.target = ctl.target
                    if stream:
                        stream.target = ctl.target
                    print(f"  target is now {ctl.target}")

            if wait_for_start:
                kp0, _ = frames[0]
                while not ctl.take_start():
                    apply_settings()
                    st = eng2.update(kp0, time.time())
                    if stream:
                        stream.send(kp0, 0.0, st, None)
                    time.sleep(0.05)
                print(f"--- start (session {loop}) ---")

            wall0 = time.time()
            last_phase = None
            for i, (kp, t) in enumerate(frames):
                if a.speed > 0:
                    due = wall0 + (t - t0_data) / a.speed
                    dt = due - time.time()
                    if dt > 0:
                        time.sleep(dt)
                apply_settings()
                st = eng2.update(kp, wall0 + (t - t0_data))
                rep = st["last_rep"] if st["rep_completed"] else None
                if stream:
                    stream.send(disp[i] if disp is not None else kp, t, st, rep, measure_kp=kp)
                if not a.quiet:
                    if st["phase"] != last_phase:
                        print(f"  phase -> {st['phase']:8s} knee={st['knee_angle']} "
                              f"pelvis={st['pelvis_h']}")
                        last_phase = st["phase"]
                    if st["live_cue"]:
                        print(f"  LIVE: {st['live_cue']}")
                    if rep:
                        print(f"REP {rep['rep']}: performed={rep['variation']} "
                              f"target={rep['target_depth']} met={rep['depth_met']} "
                              f"faults={rep['faults']}")
                        for c in rep.get("cues", []):
                            print(f"    - {c}")
            loop += 1
            if a.once:
                break
            print(f"--- session {loop - 1} finished, back to the setup screen ---")
    except KeyboardInterrupt:
        pass
    finally:
        if ctl is not None:
            ctl.stop()
        if stream:
            stream.close()
        print("\nstopped.")


if __name__ == "__main__":
    main()
