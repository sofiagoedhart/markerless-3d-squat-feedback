using System.Collections.Generic;
using UnityEngine;
using SimpleJSON;

public class SMPLXPoseDriver : MonoBehaviour
{
    [Header("Wiring")]
    public PoseUdpReceiver receiver;
    [Tooltip("The GameObject holding the SMPLX component (e.g. smplx-neutral).")]
    public Transform avatarRoot;

    [Header("Positioning")]
    public bool followHeight = true;
    [Tooltip("Let the avatar drift sideways / forwards with the subject. Off keeps it centred on camera.")]
    public bool followHorizontal = false;
    [Tooltip("Anchor the avatar horizontally by its feet instead of its pelvis, so the feet do not slide.")]
    public bool anchorToFeet = true;
    [Tooltip("Ankle joint to sole in metres; reduce if the avatar floats, increase if it sinks.")]
    public float footDropM = 0.07f;

    [Tooltip("Put the lowest sole on the floor every frame.")]
    public bool lockFeetToFloor = true;
    [Tooltip("World Y of the floor the avatar stands on.")]
    public float floorY = 0f;

    [Header("Arms")]
    [Tooltip("Drive the arms from the data; off holds them in a fixed bar-hold pose.")]
    public bool driveArms = false;
    [Tooltip("How far the upper arms hang below horizontal, in degrees.")]
    public float shoulderDropDeg = 48f;
    [Tooltip("How far the elbows are bent, in degrees. Negative flips the bend.")]
    public float elbowBendDeg = -100f;

    [Header("Height scale")]
    [Tooltip("Scale the avatar once to the athlete's height measured at calibration.")]
    public bool applyHeightScale = true;
    [Tooltip("Correction for the shoulder keypoint and shoulder bone not being the same point.")]
    public float scaleTrim = 1.0f;
    [Tooltip("Refuse scales outside this range - a bad calibration should give a " +
             "wrong-looking avatar, not a giant or an ant.")]
    public float minScale = 0.7f;
    public float maxScale = 1.4f;

    [Header("Filtering")]
    [Range(0f, 1f)]
    [Tooltip("Rotation smoothing: 0 is raw, 0.3-0.5 is visually smooth (display only).")]
    public float smoothing = 0.3f;

    [Range(0f, 1f)]
    [Tooltip("Smoothing for the avatar's position (display only).")]
    public float positionSmoothing = 0.5f;

    [Header("Foot IK")]
    [Tooltip("Solve the legs to the measured ankle positions instead of copying joint angles.")]
    public bool enableFootIK = false;
    [Range(0f, 1f)]
    [Tooltip("Blend between the rotation-driven pose (0) and the IK solution (1). " +
             "Useful for showing the difference side by side.")]
    public float footIKWeight = 1f;
    [Tooltip("Raise (+) or lower (-) the ankle targets, in metres.")]
    public float footIKLift = 0f;

    [Header("Dropouts")]
    [Tooltip("Seconds the avatar keeps easing toward the last pose when no person is detected.")]
    public float dropoutHold = 0.5f;
    [Tooltip("Pace the smoothing to the data rate rather than the render rate.")]
    public bool paceToDataRate = true;

    [Header("Debug")]
    [Tooltip("Log pelvis / ankle / sole heights once a second. Turn this on " +
             "before guessing at any vertical problem.")]
    public bool logHeights = false;
    public bool drawStickFigure = true;
    public bool logOnce = true;

    enum LongAxis { ToChild, BodyUp, BodyForward }
    enum RefAxis { BodyRight, BodyUp, BodyForward}

    class Seg
    {
        public string name;
        public string boneName, childName;
        public LongAxis longAxis;
        public RefAxis refAxis;
        public Transform bone, child;
        public Quaternion correction = Quaternion.identity;
        public bool ready;
        public Quaternion target = Quaternion.identity;
        public bool hasTarget;
        public Quaternion smoothed = Quaternion.identity;
        public bool hasSmoothed;
    }

    static readonly Seg[] TABLE = new Seg[]
    {
        new Seg { name="pelvis",          boneName="pelvis",          longAxis=LongAxis.BodyUp,      refAxis=RefAxis.BodyRight },
        new Seg { name="spine1",          boneName="spine1",          childName="spine2",     longAxis=LongAxis.ToChild, refAxis=RefAxis.BodyRight },
        new Seg { name="neck",            boneName="neck",            childName="head",       longAxis=LongAxis.ToChild, refAxis=RefAxis.BodyRight },
        new Seg { name="left_hip",        boneName="left_hip",        childName="left_knee",  longAxis=LongAxis.ToChild, refAxis=RefAxis.BodyRight },
        new Seg { name="left_knee",       boneName="left_knee",       childName="left_ankle", longAxis=LongAxis.ToChild, refAxis=RefAxis.BodyRight },
        new Seg { name="left_ankle",      boneName="left_ankle",      longAxis=LongAxis.BodyForward, refAxis=RefAxis.BodyUp },
        new Seg { name="right_hip",       boneName="right_hip",       childName="right_knee", longAxis=LongAxis.ToChild, refAxis=RefAxis.BodyRight },
        new Seg { name="right_knee",      boneName="right_knee",      childName="right_ankle",longAxis=LongAxis.ToChild, refAxis=RefAxis.BodyRight },
        new Seg { name="right_ankle",     boneName="right_ankle",     longAxis=LongAxis.BodyForward, refAxis=RefAxis.BodyUp },
        new Seg { name="left_shoulder",   boneName="left_shoulder",   childName="left_elbow", longAxis=LongAxis.ToChild, refAxis=RefAxis.BodyForward },
        new Seg { name="left_elbow",      boneName="left_elbow",      childName="left_wrist", longAxis=LongAxis.ToChild, refAxis=RefAxis.BodyForward },
        new Seg { name="right_shoulder",  boneName="right_shoulder",  childName="right_elbow",longAxis=LongAxis.ToChild, refAxis=RefAxis.BodyForward },
        new Seg { name="right_elbow",     boneName="right_elbow",     childName="right_wrist",longAxis=LongAxis.ToChild, refAxis=RefAxis.BodyForward },
    };

    static readonly int[,] COCO_LINKS = {
        {5,6},{5,7},{7,9},{6,8},{8,10},{5,11},{6,12},{11,12},
        {11,13},{13,15},{12,14},{14,16},{0,5},{0,6}
    };

    Transform _pelvis;
    Vector3 _startPos;
    bool _init;
    Vector3 _wantSmooth, _wantRaw;
    bool _haveWant;
    int _lastPacketCount = -1;
    float _pktInterval = 0.118f;
    float _gapSeconds, _lastPacketAt;
    bool _wasDropped;
    bool _warnedNoFollowHeight;
    float _lastHeightLog;
    float _avatarLeg = 0f;
    Transform _lAnk, _rAnk;
    Transform _lHipB, _lKneB, _rHipB, _rKneB;
    Vector3 _lAnkTgt, _rAnkTgt;
    bool _haveLAnk, _haveRAnk;
    float _appliedScale = 1f;
    Vector3 _baseScale = Vector3.one;
    bool _scaleApplied;

    /// Point the driver at a different SMPL-X rig at runtime and re-measure everything that was measured from the old one.
    public void SwitchAvatar(Transform root)
    {
        if (root == null || root == avatarRoot) return;
        if (avatarRoot != null) avatarRoot.localScale = _baseScale;
        _appliedScale = 1f;
        avatarRoot = root;
        foreach (var s in TABLE)
        {
            s.bone = s.child = null;
            s.ready = false;
            s.hasTarget = false;
            s.hasSmoothed = false;
            s.correction = Quaternion.identity;
        }
        _pelvis = _lAnk = _rAnk = null;
        _scaleApplied = false;
        enabled = true;
        _startPos = avatarRoot.position;
        CaptureRestPose();
    }

    void Start()
    {
        if (avatarRoot == null)
        {
            Debug.LogError("[SMPLXPoseDriver] avatarRoot is not assigned.");
            enabled = false; return;
        }
        if (receiver == null) receiver = FindAnyObjectByType<PoseUdpReceiver>();
        _startPos = avatarRoot.position;
        CaptureRestPose();
    }

    /// Right-click the component > Reset To Working Defaults.
    [ContextMenu("Reset To Working Defaults")]
    public void ResetToWorkingDefaults()
    {
        followHeight = true;
        followHorizontal = true;
        anchorToFeet = true;
        lockFeetToFloor = true;
        footDropM = 0.07f;
        enableFootIK = false;
        footIKWeight = 1f;
        footIKLift = 0f;
        applyHeightScale = true;
        scaleTrim = 1f;
        smoothing = 0.5f;
        positionSmoothing = 0.5f;
        paceToDataRate = true;
        dropoutHold = 0.5f;
        driveArms = false;
        Debug.Log("[SMPLXPoseDriver] reset to working defaults.");
    }

    void CaptureRestPose()
    {
        var byName = new Dictionary<string, Transform>();
        foreach (Transform t in avatarRoot.GetComponentsInChildren<Transform>(true))
            byName[t.name] = t;

        foreach (var s in TABLE)
        {
            byName.TryGetValue(s.boneName, out s.bone);
            if (s.childName != null) byName.TryGetValue(s.childName, out s.child);
        }
        byName.TryGetValue("pelvis", out _pelvis);
        if (_pelvis == null)
        {
            Debug.LogError("[SMPLXPoseDriver] no bone named 'pelvis' under avatarRoot - " +
                           "is avatarRoot really the SMPL-X prefab?");
            enabled = false; return;
        }

        bool IsArm(string n) => n.EndsWith("_shoulder") || n.EndsWith("_elbow");

        foreach (var s in TABLE) if (s.bone != null) s.bone.localRotation = Quaternion.identity;

        Transform lhip = null, rhip = null, spine3 = null;
        byName.TryGetValue("left_hip", out lhip);
        byName.TryGetValue("right_hip", out rhip);
        byName.TryGetValue("spine3", out spine3);
        if (lhip == null || rhip == null || spine3 == null)
        {
            Debug.LogError("[SMPLXPoseDriver] the rig is missing left_hip / right_hip / spine3, " +
                           "so its anatomical axes cannot be measured.");
            enabled = false; return;
        }
        Vector3 right = (rhip.position - lhip.position).normalized;
        Vector3 up = (spine3.position - _pelvis.position).normalized;
        up = (up - Vector3.Dot(up, right) * right).normalized;
        Vector3 fwd = Vector3.Cross(right, up);

        if (!driveArms)
        {
            SetLocal(byName, "left_shoulder",  0, 0,  shoulderDropDeg);
            SetLocal(byName, "right_shoulder", 0, 0, -shoulderDropDeg);
            SetLocal(byName, "left_elbow",     0, 0,  elbowBendDeg);
            SetLocal(byName, "right_elbow",    0, 0, -elbowBendDeg);
        }

        _baseScale = avatarRoot.localScale;
        byName.TryGetValue("left_ankle", out _lAnk);
        byName.TryGetValue("right_ankle", out _rAnk);
        byName.TryGetValue("left_hip", out _lHipB);
        byName.TryGetValue("left_knee", out _lKneB);
        byName.TryGetValue("right_hip", out _rHipB);
        byName.TryGetValue("right_knee", out _rKneB);
        Transform lhip2 = null, rhip2 = null;
        byName.TryGetValue("left_hip", out lhip2);
        byName.TryGetValue("right_hip", out rhip2);
        if (_lAnk && _rAnk && lhip2 && rhip2)
        {
            Vector3 mAnk = (_lAnk.position + _rAnk.position) * 0.5f;
            Vector3 mHip = (lhip2.position + rhip2.position) * 0.5f;
            float sx = Mathf.Abs(_baseScale.x) < 1e-6f ? 1f : _baseScale.x;
            _avatarLeg = Vector3.Distance(mAnk, mHip) / sx;
        }
        else
        {
            Debug.LogWarning("[SMPLXPoseDriver] hip/ankle bones not found - " +
                             "height scaling and foot lock disabled for this rig.");
        }

        int ok = 0;
        foreach (var s in TABLE)
        {
            if (s.bone == null) { Debug.LogWarning($"[SMPLXPoseDriver] missing bone {s.boneName}"); continue; }
            if (!driveArms && IsArm(s.name)) continue;
            Vector3 lng;
            switch (s.longAxis)
            {
                case LongAxis.BodyUp: lng = up; break;
                case LongAxis.BodyForward: lng = fwd; break;
                default:
                    if (s.child == null) { Debug.LogWarning($"[SMPLXPoseDriver] missing child {s.childName}"); continue; }
                    lng = (s.child.position - s.bone.position);
                    break;
            }
            Vector3 rf = s.refAxis == RefAxis.BodyRight ? right 
                        :s.refAxis == RefAxis.BodyUp    ? up
                        :                                 fwd;
            if (!FromAxes(lng, rf, out Quaternion qRest)) continue;
            s.correction = Quaternion.Inverse(qRest) * s.bone.rotation;
            s.ready = true;
            ok++;
        }
        _init = true;
        Debug.Log($"[SMPLXPoseDriver] rest pose captured, {ok}/{TABLE.Length} segments ready.");
    }

    static void SetLocal(Dictionary<string, Transform> byName, string bone,
                         float x, float y, float z)
    {
        if (byName.TryGetValue(bone, out Transform t) && t != null)
            t.localRotation = Quaternion.Euler(x, y, z);
    }

    /// Orthonormal frame from a longitudinal axis and a reference axis, as a rotation.
    static bool FromAxes(Vector3 lng, Vector3 rf, out Quaternion q)
    {
        q = Quaternion.identity;
        if (lng.sqrMagnitude < 1e-9f) return false;
        Vector3 e1 = lng.normalized;
        Vector3 r = rf - Vector3.Dot(rf, e1) * e1;
        if (r.magnitude < 0.15f) return false;
        Vector3 e2 = r.normalized;
        Vector3 e3 = Vector3.Cross(e1, e2);
        q = Quaternion.LookRotation(e3, e2);
        return true;
    }

    void LateUpdate()
    {
        if (!_init || receiver == null || receiver.Latest == null) return;
        JSONNode pkt = receiver.Latest;

        if (receiver.PacketCount != _lastPacketCount)
        {
            if (_lastPacketCount >= 0)
            {
                float dtPkt = Mathf.Clamp(Time.time - _lastPacketAt, 0.01f, 1.0f);
                _pktInterval = Mathf.Lerp(_pktInterval, dtPkt, 0.15f);
            }
            _lastPacketAt = Time.time;
            _lastPacketCount = receiver.PacketCount;
        }

        bool fresh = pkt["present"].AsInt != 0;
        if (fresh) { _gapSeconds = 0f; if (_wasDropped) _wasDropped = false; }
        else
        {
            _gapSeconds += Time.deltaTime;
            if (_gapSeconds > dropoutHold)
            {
                if (!_wasDropped)
                {
                    _wasDropped = true;
                    Debug.Log($"[SMPLXPoseDriver] no subject for {_gapSeconds:F2}s - holding pose.");
                }
                return;
            }
        }

        float k;
        if (paceToDataRate)
        {
            float tau = Mathf.Max(_pktInterval, 0.02f) * Mathf.Lerp(0.35f, 1.4f, Mathf.Clamp01(smoothing));
            k = 1f - Mathf.Exp(-Time.deltaTime / tau);
        }
        else
        {
            k = (smoothing <= 0f) ? 1f
              : 1f - Mathf.Pow(Mathf.Clamp01(smoothing), Mathf.Max(Time.deltaTime * 60f, 1e-4f));
        }

        JSONNode seg = fresh ? pkt["seg"] : null;
        if (seg != null)
        {
            foreach (var s in TABLE)
            {
                if (!s.ready) continue;
                JSONNode a = seg[s.name];
                if (a == null || a.Count < 6) continue;
                Vector3 lng = new Vector3(a[0].AsFloat, a[1].AsFloat, a[2].AsFloat);
                Vector3 rf = new Vector3(a[3].AsFloat, a[4].AsFloat, a[5].AsFloat);
                if (!FromAxes(lng, rf, out Quaternion qLive)) continue;
                s.target = qLive * s.correction;
                s.hasTarget = true;
            }
        }
        foreach (var s in TABLE)
        {
            if (!s.ready || !s.hasTarget) continue;
            if (!s.hasSmoothed) { s.smoothed = s.target; s.hasSmoothed = true; }
            else s.smoothed = (k >= 1f) ? s.target : Quaternion.Slerp(s.smoothed, s.target, k);
            s.bone.rotation = s.smoothed;
        }

        if (applyHeightScale && !_scaleApplied && _avatarLeg > 1e-4f)
        {
            JSONNode subj = pkt["subject"];
            if (subj != null && !subj.IsNull)
            {
                float subjM = subj["hip_ankle_mm"].AsFloat / 1000f;
                if (subjM > 1e-4f)
                {
                    float sc = (subjM / _avatarLeg) * scaleTrim;
                    if (sc >= minScale && sc <= maxScale)
                    {
                        avatarRoot.localScale = _baseScale * sc;
                        _appliedScale = sc;
                        _scaleApplied = true;
                        Debug.Log($"[SMPLXPoseDriver] height scale {sc:F3} " +
                                  $"(subject leg {subjM * 1000f:F0} mm / avatar leg " +
                                  $"{_avatarLeg * 1000f:F0} mm, trim {scaleTrim:F2}). " +
                                  "Frozen for this session.");
                    }
                    else
                    {
                        _scaleApplied = true;
                        Debug.LogWarning($"[SMPLXPoseDriver] computed height scale {sc:F3} is " +
                                         $"outside [{minScale}, {maxScale}] - left at 1.0. " +
                                         "Check the standing calibration.");
                    }
                }
            }
        }

        JSONNode root = fresh ? pkt["root"] : null;
        if (root != null && root.Count >= 3)
            _wantRaw = new Vector3(root[0].AsFloat, root[1].AsFloat + footDropM, root[2].AsFloat);

        if (_haveWant || (root != null && root.Count >= 3))
        {
            if (!_haveWant) { _wantSmooth = _wantRaw; _haveWant = true; }
            else
            {
                float kp2;
                if (paceToDataRate)
                {
                    float tauP = Mathf.Max(_pktInterval, 0.02f)
                               * Mathf.Lerp(0.35f, 1.4f, Mathf.Clamp01(positionSmoothing));
                    kp2 = 1f - Mathf.Exp(-Time.deltaTime / tauP);
                }
                else
                {
                    kp2 = (positionSmoothing <= 0f) ? 1f
                        : 1f - Mathf.Pow(Mathf.Clamp01(positionSmoothing),
                                         Mathf.Max(Time.deltaTime * 60f, 1e-4f));
                }
                _wantSmooth = Vector3.Lerp(_wantSmooth, _wantRaw, kp2);
            }
            Vector3 want = _wantSmooth;

            Vector3 delta = want - _pelvis.position;

            if (anchorToFeet && _lAnk && _rAnk && _haveLAnk && _haveRAnk)
            {
                Vector3 avatarMidAnk = (_lAnk.position + _rAnk.position) * 0.5f;
                Vector3 measuredMidAnk = (_lAnkTgt + _rAnkTgt) * 0.5f;
                delta.x = measuredMidAnk.x - avatarMidAnk.x;
                delta.z = measuredMidAnk.z - avatarMidAnk.z;
            }

            if (!followHorizontal) { delta.x = 0f; delta.z = 0f; }
            if (!followHeight) delta.y = 0f;
            avatarRoot.position += delta;
            if (!followHorizontal)
            {
                Vector3 p = avatarRoot.position;
                avatarRoot.position = new Vector3(_startPos.x, p.y, _startPos.z);
            }
        }

        if ((enableFootIK && footIKWeight > 0.001f) || anchorToFeet)
        {
            if (!followHeight)
            {
                if (!_warnedNoFollowHeight)
                {
                    _warnedNoFollowHeight = true;
                    Debug.LogWarning("[SMPLXPoseDriver] Foot IK needs Follow Height ON - " +
                                     "nothing is controlling the avatar's vertical position. " +
                                     "Skipping IK this session until it is enabled.");
                }
            }
            else
            {
            float lift = footDropM * _appliedScale + footIKLift;
            Vector3 up = Vector3.up * lift;

            if (fresh)
            {
                JSONNode j = pkt["joints"];
                if (j != null && j.Count >= 17)
                {
                    if (TryJoint(j, 15, out Vector3 lp)) { Latch(ref _lAnkTgt, ref _haveLAnk, lp + up, k); }
                    if (TryJoint(j, 16, out Vector3 rp)) { Latch(ref _rAnkTgt, ref _haveRAnk, rp + up, k); }
                }
            }

            if (enableFootIK && footIKWeight > 0.001f)
            {
                if (_haveLAnk)
                    SolveLeg(_lHipB, _lKneB, _lAnk,
                             new Vector3(_lAnkTgt.x, _lAnk.position.y, _lAnkTgt.z));
                if (_haveRAnk)
                    SolveLeg(_rHipB, _rKneB, _rAnk,
                             new Vector3(_rAnkTgt.x, _rAnk.position.y, _rAnkTgt.z));
            }
            }
        }

        if (lockFeetToFloor && followHeight && _lAnk && _rAnk)
        {
            float soleY = Mathf.Min(_lAnk.position.y, _rAnk.position.y)
                          - footDropM * _appliedScale;
            Vector3 p2 = avatarRoot.position;
            avatarRoot.position = new Vector3(p2.x, p2.y + (floorY - soleY), p2.z);
        }

        if (logHeights && Time.time - _lastHeightLog > 1f && _lAnk && _rAnk)
        {
            _lastHeightLog = Time.time;
            float sole = Mathf.Min(_lAnk.position.y, _rAnk.position.y)
                       - footDropM * _appliedScale;
            Debug.Log($"[SMPLXPoseDriver] pelvis {_pelvis.position.y:F3}  " +
                      $"ankleL {_lAnk.position.y:F3} ankleR {_rAnk.position.y:F3}  " +
                      $"sole {sole:F3}  target floorY {floorY:F3}  " +
                      $"scale {_appliedScale:F3}  footDropM {footDropM:F3}");
        }

        if (drawStickFigure) DrawStickFigure(pkt["joints"]);

        if (logOnce)
        {
            logOnce = false;
            Debug.Log($"[SMPLXPoseDriver] first packet applied: {(seg == null ? 0 : seg.Count)} segments.");
        }
    }

    /// A joint that was not reconstructed this frame arrives as JSON null.
    static bool TryJoint(JSONNode j, int i, out Vector3 p)
    {
        p = Vector3.zero;
        JSONNode n = j[i];
        if (n == null || n.IsNull || n.Count < 3) return false;
        p = new Vector3(n[0].AsFloat, n[1].AsFloat, n[2].AsFloat);
        return !(float.IsNaN(p.x) || float.IsNaN(p.y) || float.IsNaN(p.z));
    }

    static void Latch(ref Vector3 cur, ref bool have, Vector3 want, float k)
    {
        if (!have) { cur = want; have = true; }
        else cur = Vector3.Lerp(cur, want, k);
    }

    /// Analytic two-bone IK: put `ankle` on `target` by rotating `hip` and `knee`.
    void SolveLeg(Transform hip, Transform knee, Transform ankle, Vector3 target)
    {
        if (hip == null || knee == null || ankle == null) return;

        Vector3 a = hip.position, b = knee.position, c = ankle.position;
        float upper = Vector3.Distance(a, b);
        float lower = Vector3.Distance(b, c);
        if (upper < 1e-5f || lower < 1e-5f) return;

        Vector3 toTarget = target - a;
        float d = toTarget.magnitude;
        if (d < 1e-5f) return;
        Vector3 dir = toTarget / d;

        float dMin = Mathf.Abs(upper - lower) + 1e-3f;
        float dMax = (upper + lower) * 0.999f;
        float dEff = Mathf.Clamp(d, dMin, dMax);
        Vector3 effTarget = a + dir * dEff;

        Vector3 bend = (b - a) - Vector3.Dot(b - a, dir) * dir;
        if (bend.sqrMagnitude < 1e-8f)
        {
            bend = Vector3.ProjectOnPlane(hip.forward, dir);
            if (bend.sqrMagnitude < 1e-8f) bend = Vector3.ProjectOnPlane(Vector3.forward, dir);
            if (bend.sqrMagnitude < 1e-8f) return;
        }
        bend.Normalize();

        float x = (upper * upper - lower * lower + dEff * dEff) / (2f * dEff);
        float h2 = upper * upper - x * x;
        float h = h2 > 0f ? Mathf.Sqrt(h2) : 0f;
        Vector3 kneeGoal = a + dir * x + bend * h;

        Quaternion hip0 = hip.rotation, knee0 = knee.rotation;

        Quaternion qh = Quaternion.FromToRotation(b - a, kneeGoal - a) * hip.rotation;
        if (!IsFinite(qh)) return;
        hip.rotation = qh;

        Vector3 b2 = knee.position, c2 = ankle.position;
        Quaternion qk = Quaternion.FromToRotation(c2 - b2, effTarget - b2) * knee.rotation;
        if (!IsFinite(qk)) { hip.rotation = hip0; return; }
        knee.rotation = qk;

        if (footIKWeight < 0.999f)
        {
            hip.rotation = Quaternion.Slerp(hip0, hip.rotation, footIKWeight);
            knee.rotation = Quaternion.Slerp(knee0, knee.rotation, footIKWeight);
        }
    }

    static bool IsFinite(Quaternion q) =>
        !(float.IsNaN(q.x) || float.IsNaN(q.y) || float.IsNaN(q.z) || float.IsNaN(q.w))
        && (q.x * q.x + q.y * q.y + q.z * q.z + q.w * q.w) > 1e-6f;

    void DrawStickFigure(JSONNode j)
    {
        if (j == null || j.Count < 17) return;
        Vector3? P(int i)
        {
            JSONNode n = j[i];
            if (n == null || n.IsNull || n.Count < 3) return null;
            return new Vector3(n[0].AsFloat, n[1].AsFloat + footDropM, n[2].AsFloat);
        }
        for (int i = 0; i < COCO_LINKS.GetLength(0); i++)
        {
            Vector3? a = P(COCO_LINKS[i, 0]), b = P(COCO_LINKS[i, 1]);
            if (a.HasValue && b.HasValue) Debug.DrawLine(a.Value, b.Value, Color.green);
        }
    }
}
