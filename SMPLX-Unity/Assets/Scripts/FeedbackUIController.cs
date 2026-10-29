using UnityEngine;
using UnityEngine.UIElements;
using SimpleJSON;

[RequireComponent(typeof(UIDocument))]
public class FeedbackUIController : MonoBehaviour
{
    public PoseUdpReceiver receiver;

    int repTarget => SessionSettings.RepTarget;

    [Header("Depth column range (mm of hip above knee)")]
    [Tooltip("Value at the TOP of the column — roughly the standing hip-to-knee gap.")]
    public float topMm = 450f;
    [Tooltip("Value at the BOTTOM of the column — deeper than anyone will squat.")]
    public float bottomMm = -200f;

    [Header("Cue")]
    [Tooltip("Seconds a live cue stays up after the fault clears, so it does not " +
             "flicker on and off while the athlete is correcting.")]
    public float cueHold = 1.2f;

    [Header("Tracking lost")]
    public string lostTitle = "Tracking lost";
    public string lostBody = "Step back into view of all three cameras.";

    [Header("Depth trajectory (split screen)")]
    [Tooltip("Camera whose viewport is shrunk to the top of the screen. Empty = Camera.main.")]
    public Camera splitCamera;
    [Range(0.2f, 0.5f)]
    [Tooltip("Fraction of the screen height given to the chart below the gym view.")]
    public float splitFraction = 0.36f;
    public float chartTopMm = 470f;
    public float chartBottomMm = -80f;
    [Tooltip("Seconds of history the trajectory shows; it scrolls once this fills.")]
    public float chartWindowSeconds = 15f;
    public Color traceColor = new Color(0.165f, 0.471f, 0.839f);

    [Header("Keys")]
    public KeyCode toggleDiagnostics = KeyCode.D;
    public KeyCode toggleUI = KeyCode.H;

    UIDocument _doc;
    VisualElement _root;
    VisualElement _depthCard;
    VisualElement _repCard, _pipRow, _band, _fill, _marker, _cueCard, _countCard;
    Label _countNum;
    Label _repCaption, _repCount, _repOf, _targetName, _you, _targetTick,
          _cueTitle, _cueBody, _phase, _status, _diag;

    readonly LiveDepthChart _chart = new LiveDepthChart();
    ScreenFlowController _flow;
    int _pipCount = -1;
    float _cueUntil = -1f;
    bool _diagOn;

    void OnEnable()
    {
        _doc = GetComponent<UIDocument>();
        if (receiver == null) receiver = FindAnyObjectByType<PoseUdpReceiver>();
        if (_flow == null) _flow = FindAnyObjectByType<ScreenFlowController>();
        _chart.Reset();
    }

    void OnDisable()
    {
        ApplySplit(false);
        _chart.Reset();
    }

    /// Splits the screen between the avatar and the depth chart.
    void ApplySplit(bool on)
    {
        var cam = splitCamera != null ? splitCamera : Camera.main;
        if (cam == null) return;
        float f = Mathf.Clamp(splitFraction, 0.2f, 0.5f);
        Rect want = on ? new Rect(0f, f, 1f, 1f - f) : new Rect(0f, 0f, 1f, 1f);
        if (cam.rect != want) { cam.rect = want; cam.ResetAspect(); }
        if (_chart.Panel != null) _chart.Panel.style.height = Length.Percent(f * 100f);
    }

    T Get<T>(string name) where T : VisualElement
    {
        var e = _root.Q<T>(name);
        if (e == null)
            Debug.LogWarning($"[FeedbackUI] no element named '{name}' in the UXML — " +
                             "that part of the interface will simply not update.");
        return e;
    }

    /// Re-binds whenever the UIDocument hands out a NEW visual tree, not just once at startup.
    bool Bind()
    {
        var root = _doc != null ? _doc.rootVisualElement : null;
        if (root == null) return false;
        if (root == _root) return true;

        _root = root;
        _root.pickingMode = PickingMode.Ignore;
        _pipCount = -1;

        _root.style.flexGrow = 1;
        for (int i = 0; i < _root.childCount; i++)
        {
            var c = _root[i];
            c.style.position = Position.Absolute;
            c.style.left = 0; c.style.top = 0; c.style.right = 0; c.style.bottom = 0;
        }

        _repCard    = Get<VisualElement>("rep-card");
        _depthCard  = Get<VisualElement>("depth-card");
        _repCaption = Get<Label>("rep-caption");
        _repCount   = Get<Label>("rep-count");
        _repOf      = Get<Label>("rep-of");
        _pipRow     = Get<VisualElement>("rep-pips");
        _targetName = Get<Label>("target-name");
        _band       = Get<VisualElement>("depth-band");
        _fill       = Get<VisualElement>("depth-fill");
        _marker     = Get<VisualElement>("depth-marker");
        _you        = Get<Label>("depth-you");
        _targetTick = Get<Label>("depth-target-tick");
        _cueCard    = Get<VisualElement>("cue-card");
        _countCard  = Get<VisualElement>("countdown-card");
        _countNum   = Get<Label>("countdown-num");
        _cueTitle   = Get<Label>("cue-title");
        _cueBody    = Get<Label>("cue-body");
        _phase      = Get<Label>("phase");
        _status     = Get<Label>("status");
        _diag       = Get<Label>("diagnostics");
        _chart.Bind(_root);
        Debug.Log("[FeedbackUI] bound to the visual tree.");
        return true;
    }

    /// One pip per rep in the target.
    void BuildPips()
    {
        if (_pipRow == null) return;
        if (_pipCount == repTarget && _pipRow.childCount == repTarget) return;
        _pipRow.Clear();
        for (int i = 0; i < repTarget; i++)
        {
            var pip = new VisualElement();
            pip.AddToClassList("pip");
            _pipRow.Add(pip);
        }
        _pipCount = repTarget;
    }

    void Update()
    {
        if (!Bind()) return;
        BuildPips();

        var depthMode = SessionSettings.LiveDepthMode;
        bool traj = depthMode == SessionSettings.LiveDepth.Trajectory;
        bool onLive = _flow == null || _flow.Current == ScreenFlowController.Screen.Live;
        Show(_chart.Panel, traj && onLive);
        ApplySplit(traj && onLive);
        _chart.topMm = chartTopMm; _chart.bottomMm = chartBottomMm;
        _chart.windowSeconds = Mathf.Max(3f, chartWindowSeconds); _chart.traceColor = traceColor;

        if (Input.GetKeyDown(toggleUI))
            _root.style.display = _root.style.display == DisplayStyle.None
                                ? DisplayStyle.Flex : DisplayStyle.None;
        if (Input.GetKeyDown(toggleDiagnostics)) { _diagOn = !_diagOn; Show(_diag, _diagOn); }

        bool live = receiver != null && receiver.IsLive;
        if (_status != null)
            _status.text = live
                ? $"connected · {receiver.PacketCount} packets · H hides the overlay, D shows numbers"
                : "waiting for pose stream on UDP 5006 — run:  python src/live_form_feedback.py 0 1 2 --stream --unity-setup";
        bool tracking = live && receiver.Latest != null
                        && receiver.Latest["present"].AsInt != 0;
        if (!tracking) { ShowLost(); return; }

        JSONNode cd = receiver.Latest["state"]["countdown"];
        bool counting = cd != null && !cd.IsNull;
        Show(_countCard, counting);
        if (counting && _countNum != null)
            _countNum.text = Mathf.CeilToInt(cd.AsFloat).ToString();

        JSONNode pkt = receiver.Latest;
        JSONNode st = pkt["state"];
        if (st == null || st.IsNull) return;

        int reps = st["rep"].IsNull ? 0 : st["rep"].AsInt;
        if (_repCount != null) _repCount.text = reps.ToString();
        if (_repOf != null) _repOf.text = $"of {repTarget}";
        if (_pipRow != null)
            for (int i = 0; i < _pipRow.childCount; i++)
                _pipRow[i].EnableInClassList("pip--on", i < reps);

        bool complete = reps >= repTarget;
        _repCard?.EnableInClassList("complete", complete);

        Show(_repCard, SessionSettings.ShowRepCount);
        Show(_depthCard, depthMode == SessionSettings.LiveDepth.Bar);
        if (traj) _chart.Tick(receiver, st, repTarget);
        if (_repCaption != null) _repCaption.text = complete ? "SET TARGET REACHED" : "REPS";

        if (_phase != null) _phase.text = PhaseWord(st["phase"].Value);

        JSONNode tgt = st["depth_target"];
        bool haveTgt = tgt != null && !tgt.IsNull && tgt["hi"] != null && !tgt["hi"].IsNull;
        bool openLo = haveTgt && (tgt["lo"] == null || tgt["lo"].IsNull);
        float lo = haveTgt && !openLo ? tgt["lo"].AsFloat : float.PositiveInfinity;
        float hi = haveTgt ? tgt["hi"].AsFloat : float.NegativeInfinity;
        Show(_band, haveTgt);
        Show(_targetTick, haveTgt);
        if (_targetName != null)
            _targetName.text = haveTgt ? tgt["name"].Value.ToUpper() : "";
        if (haveTgt) SetBand(openLo ? bottomMm : lo, hi);
        bool haveDepth = !st["depth_mm"].IsNull;
        Show(_marker, haveDepth); Show(_you, haveDepth); Show(_fill, haveDepth);
        if (haveDepth)
            SetDepth(st["depth_mm"].AsFloat,
                     openLo ? float.NegativeInfinity : lo, hi);

        string cue = !st["cue"].IsNull ? st["cue"].Value : null;
        if (!string.IsNullOrEmpty(cue))
        {
            if (_cueBody != null) _cueBody.text = cue;
            if (_cueTitle != null)
                _cueTitle.text = st["cue_short"].IsNull ? "Fix your form" : st["cue_short"].Value;
            _cueUntil = Time.time + cueHold;
        }
        Show(_cueCard, Time.time < _cueUntil);

        if (_diagOn && _diag != null)
            _diag.text = $"phase {st["phase"].Value}   seq {pkt["seq"].Value}\n" +
                         $"knee {st["knee"].Value}°   pelvis {st["pelvis_h"].Value} mm\n" +
                         $"depth {st["depth_mm"].Value} mm\n" +
                         $"target {(tgt != null ? tgt["name"].Value : "?")} " +
                         (haveTgt ? $"[{(openLo ? "open" : lo.ToString("0"))}, {hi:0}] mm" : "none");
    }

    /// The tracking-lost state: no depth marker, no stale cue, one plain message.
    void ShowLost()
    {
        Show(_marker, false); Show(_you, false); Show(_fill, false);
        Show(_countCard, false);
        _chart.HideLive();
        if (_cueTitle != null) _cueTitle.text = lostTitle;
        if (_cueBody != null) _cueBody.text = lostBody;
        Show(_cueCard, true);
        _cueUntil = 0f;
        if (_phase != null) _phase.text = "";
    }

    static void Show(VisualElement e, bool on)
    {
        if (e != null) e.EnableInClassList("hidden", !on);
    }

    static string PhaseWord(string phase)
    {
        switch (phase)
        {
            case "SETUP": return "ready";
            case "DESCENT": return "going down";
            case "BOTTOM": return "at the bottom";
            case "ASCENT": return "coming up";
            default: return "";
        }
    }

    void SetBand(float lo, float hi)
    {
        float a = Mathf.Clamp01(Mathf.InverseLerp(bottomMm, topMm, lo));
        float b = Mathf.Clamp01(Mathf.InverseLerp(bottomMm, topMm, hi));

        if (_band != null)
        {
            _band.style.bottom = Length.Percent(a * 100f);
            _band.style.height = Length.Percent(Mathf.Max(b - a, 0f) * 100f);
        }
        if (_targetTick != null)
            _targetTick.style.bottom = Length.Percent((a + b) * 50f);
    }

    void SetDepth(float mm, float lo, float hi)
    {
        float f = Mathf.Clamp01(Mathf.InverseLerp(bottomMm, topMm, mm));
        if (_fill != null) _fill.style.height = Length.Percent((1f - f) * 100f);
        if (_marker != null) _marker.style.bottom = Length.Percent(f * 100f);
        if (_you != null) _you.style.bottom = Length.Percent(f * 100f);

        bool inBand = mm >= lo && mm <= hi;
        _marker?.EnableInClassList("in-band", inBand);
        _you?.EnableInClassList("in-band", inBand);
        if (_you != null) _you.text = inBand ? "You ✓" : "You";
    }
}
