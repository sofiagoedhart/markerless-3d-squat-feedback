# Markerless 3D squat form feedback

Final-year Electrical Engineering project (skripsie), Stellenbosch University, 2026.

Three webcams watch an athlete squat. Each camera finds 17 body keypoints with a YOLO11 pose model,
the three views are triangulated into one 3D skeleton in millimetres, and the skeleton is smoothed,
measured and passed through a repetition state machine that judges depth and knee tracking. The
skeleton and the verdicts are streamed to a Unity application that drives an SMPL-X avatar and shows
the live, post-repetition and post-set feedback screens. A session report is exported as HTML.

## Repository layout

| Folder | Contents |
|---|---|
| `src/` | The Python system: calibration, triangulation, smoothing, measurement, the repetition engine, the Unity stream, recording and set export, and unit tests. |
| `tools/` | Session report and review-page generators, and the avatar asset tools (texture recolouring, fist pose). |
| `SMPLX-Unity/Assets/Scripts/` | The Unity application: pose driving, screen flow, the live, post-rep and post-set screens, the setup guide and the carried barbell. |
| `SMPLX-Unity/Assets/UI/` | Screen layouts (UXML) and styles (USS). |
| `SMPLX-Unity/Assets/Editor/` | Editor tools: gym room builder, avatar recolouring, fist setup. |
| `SMPLX-Unity/Packages/`, `ProjectSettings/` | Unity project configuration (Unity 6000.5.0f1). |

## What is not included, and why

- **SMPL-X model files and the SMPL-X Unity package.** Licensed by the Max Planck Institute for
  Intelligent Systems and not redistributable. Download the Unity package from
  <https://smpl-x.is.tue.mpg.de> (registration required) and place it at `SMPLX-Unity/Assets/SMPLX/`.
  The Unity project itself started from that package's sample project, which is why
  `ProjectSettings` names the institute.
- **The Unity scene and avatar prefabs.** Both are built on the licensed SMPL-X meshes and textures.
  See *Unity setup* below to recreate them.
- **Recordings, calibration data and results.** Captured data of the author; the programs below
  regenerate all of it on a calibrated rig.
- **YOLO11 weights.** Downloaded automatically by `ultralytics` on first use.

## Python setup

Python 3.13.

```bash
python -m venv skripsie-env
source skripsie-env/bin/activate
pip install -r requirements.txt
```

Run every program from the repository root, e.g. `python src/live_form_feedback.py ...`.

## Running the system

**1. Calibrate the rig** (once, and again whenever a camera moves). Camera indices are the OS
webcam indices, reference camera first.

```bash
python src/make_chessboard.py               # printable board
python src/capture_calibration.py 0 1 2     # synchronised board images
python src/calibrate_intrinsics.py 0        # repeat for 1 and 2
python src/calibrate_extrinsics.py 0 1 2
python src/calibrate_vertical.py 0 1 2      # board flat on the floor
python src/calib_health.py 0 1 2            # start-of-session check
```

**2. Live feedback.** Start the Unity scene (Play), then:

```bash
python src/live_form_feedback.py 0 1 2 --stream --unity-setup
```

Add `--record recordings` to also save each set's raw recording. Each completed set is saved under
`results/sets/<session>/` and the session report is written to `results/sets/<session>/report.html`.

**3. Reports and review pages.**

```bash
python tools/report_session.py results/sets/<session>              # session report
python tools/export_review_html.py results/sets/<session>/<set>.json --mode set   # post-set page
python tools/export_review_html.py results/sets/<session>/<set>.json --mode rep --rep 1
```

**4. Tests.**

```bash
cd src && python test_rep_engine.py && python test_setup_stream.py
```

## Unity setup

1. Open `SMPLX-Unity/` in Unity 6000.5.0f1 after placing the SMPL-X package in `Assets/SMPLX/`.
2. Create two avatars from the package's `smplx-male` and `smplx-female` prefabs and set their shape
   values (betas) in the Inspector, then save each prefab:
   - male: `-0.08, -1.42, -0.50, -0.03, 2.99, -2.66, -1.08, 1.78, -2.94, 3.89`
   - female: `0.12, -1.63, 0.37, -0.71, 1.33, -1.68, -0.20, 0.31, 4.15, 1.11`
3. **Tools ▸ Skripsie ▸ Build Gym Room** builds the room; **Tools ▸ Skripsie ▸ Add Fists To Avatars**
   closes the hands.
4. In the scene, add `PoseUdpReceiver`, `SMPLXPoseDriver` (on each avatar), `AvatarSwitcher`,
   `AvatarFramer` (on the camera), `ScreenFlowController`, `ControlSender`, `BarHoldDetector`,
   `CarriedBarbell`, `FootTargets`, and a UI Document per screen using `Assets/UI/*.uxml` with
   `Assets/Scripts/FeedbackPanel.asset` as the panel settings, each with its controller
   (`SetupUIController`, `FeedbackUIController`, `PostRepUIController`, `PostSetUIController`).

Python streams to Unity on UDP port 5006; Unity sends settings back on port 5007.

## How the code fits together

```
3 cameras ─► YOLO11 2D pose ─► multiview_triangulate / dlt_triangulation ─► one_euro (smoothing)
         ─► metrics (geometry) ─► rep_engine (repetitions and verdicts) ─► pose_to_unity ─► Unity
                                                     │
                                       session_io / set_export ─► recordings, results, reports
```

| Python module | Role |
|---|---|
| `live_form_feedback.py` | The main program: cameras to 3D to assessment to Unity. |
| `multiview_triangulate.py`, `dlt_triangulation.py` | Triangulate the 17 keypoints from the calibrated views. |
| `one_euro.py` | The measurement smoother (and a separate, heavier one for the avatar only). |
| `metrics.py` | Joint angles, depth margin, knee separation, shoulder tilt. No decisions. |
| `rep_engine.py` | Repetition state machine, depth classification, faults and per-rep report. Thresholds at the top. |
| `pose_to_unity.py` | Converts the skeleton to avatar segment rotations and streams state and reps. |
| `control_listener.py` | Receives settings and Start / End set from Unity. |
| `session_io.py`, `set_export.py` | Recordings and saved set results. |
