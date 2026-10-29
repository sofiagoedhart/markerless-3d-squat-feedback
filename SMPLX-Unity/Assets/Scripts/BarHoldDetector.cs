using UnityEngine;
using SimpleJSON;

public class BarHoldDetector : MonoBehaviour
{
    [Tooltip("Left empty, the receiver in the scene is found automatically.")]
    public PoseUdpReceiver receiver;

    [Header("Entering the hold (strict)")]
    [Tooltip("Both elbows must be bent tighter than this (interior angle, 180 = straight).")]
    public float enterElbowDeg = 120f;
    [Tooltip("How far below the shoulder the wrist may sit, in metres.")]
    public float enterWristDrop = 0.15f;
    [Tooltip("Seconds the pose must be held before it counts.")]
    public float enterSeconds = 0.4f;

    [Header("Leaving the hold (looser)")]
    public float exitElbowDeg = 140f;
    public float exitWristDrop = 0.25f;
    [Tooltip("Seconds the pose must be lost before the hold is dropped.")]
    public float exitSeconds = 0.8f;

    [Header("Diagnostics")]
    [Tooltip("Log the measured angles once a second, for tuning on the rig.")]
    public bool logDiagnostics = false;

    /// True while the arms are in the bar hold.
    public bool Holding { get; private set; }
    /// Last measured interior elbow angles (deg), NaN when not seen.
    public float LeftElbowDeg { get; private set; } = float.NaN;
    public float RightElbowDeg { get; private set; } = float.NaN;

    [Header("Lost arms")]
    [Tooltip("Seconds without a view of both arms before a hold is dropped.")]
    public float unseenDropSeconds = 0.8f;

    float _inFor, _outFor, _nextLog, _unseenFor;

    const int L_SHO = 5, R_SHO = 6, L_ELB = 7, R_ELB = 8, L_WRI = 9, R_WRI = 10;

    void Start()
    {
        if (receiver == null) receiver = FindAnyObjectByType<PoseUdpReceiver>();
    }

    /// Drops the hold immediately.
    public void ResetHold() { Holding = false; _inFor = 0f; _outFor = 0f; _unseenFor = 0f; }

    void Update()
    {
        JSONNode j = (receiver != null && receiver.IsLive && receiver.Latest != null)
                   ? receiver.Latest["joints"] : null;
        if (j == null || j.IsNull || j.Count < 11) { Unseen(); return; }

        bool lSeen = Arm(j, L_SHO, L_ELB, L_WRI, out float lDeg, out float lDrop, out bool lDown);
        bool rSeen = Arm(j, R_SHO, R_ELB, R_WRI, out float rDeg, out float rDrop, out bool rDown);
        LeftElbowDeg = lSeen ? lDeg : float.NaN;
        RightElbowDeg = rSeen ? rDeg : float.NaN;

        if (logDiagnostics && Time.time >= _nextLog)
        {
            _nextLog = Time.time + 1f;
            Debug.Log($"[BarHold] elbow L {lDeg:F0} R {rDeg:F0} deg  wrist drop L {lDrop:F2} " +
                      $"R {rDrop:F2} m  elbows down {lDown}/{rDown}  holding {Holding}");
        }
        if (!lSeen || !rSeen) { Unseen(); return; }
        _unseenFor = 0f;

        bool enter = lDeg < enterElbowDeg && rDeg < enterElbowDeg
                  && lDrop < enterWristDrop && rDrop < enterWristDrop && lDown && rDown;
        bool keep  = lDeg < exitElbowDeg && rDeg < exitElbowDeg
                  && lDrop < exitWristDrop && rDrop < exitWristDrop;

        if (!Holding)
        {
            _inFor = enter ? _inFor + Time.deltaTime : 0f;
            if (_inFor >= enterSeconds) { Holding = true; _outFor = 0f; }
        }
        else
        {
            _outFor = keep ? 0f : _outFor + Time.deltaTime;
            if (_outFor >= exitSeconds) { Holding = false; _inFor = 0f; }
        }
    }

    /// Count time without a view of both arms, and drop the hold past the limit.
    void Unseen()
    {
        _inFor = 0f;
        _unseenFor += Time.deltaTime;
        if (Holding && _unseenFor >= unseenDropSeconds) { Holding = false; _outFor = 0f; }
    }

    /// Elbow angle and wrist and elbow positions for one arm.
    static bool Arm(JSONNode j, int s, int e, int w, out float deg, out float drop, out bool down)
    {
        deg = float.NaN; drop = float.NaN; down = false;
        if (!P(j[s], out Vector3 sh) || !P(j[e], out Vector3 el) || !P(j[w], out Vector3 wr))
            return false;
        deg = Vector3.Angle(sh - el, wr - el);
        drop = sh.y - wr.y;
        down = el.y < wr.y;
        return true;
    }

    static bool P(JSONNode n, out Vector3 p)
    {
        p = Vector3.zero;
        if (n == null || n.IsNull || n.Count < 3) return false;
        p = new Vector3(n[0].AsFloat, n[1].AsFloat, n[2].AsFloat);
        return !(float.IsNaN(p.x) || float.IsNaN(p.y) || float.IsNaN(p.z));
    }
}
