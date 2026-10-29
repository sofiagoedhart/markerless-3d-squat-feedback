using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UIElements;
using SimpleJSON;

[RequireComponent(typeof(UIDocument))]
public class PostRepUIController : MonoBehaviour
{
    public PoseUdpReceiver receiver;
    public ScreenFlowController flow;

    [Header("Depth chart range (mm of hip above knee)")]
    public float topMm = 450f;
    public float bottomMm = -80f;

    [Header("Scales")]
    [Tooltip("Full width of the left/right bar, in degrees either side of even.")]
    public float symmetryScaleDeg = 12f;
    [Tooltip("Degrees of shoulder tilt that fill the graph.")]
    public float shoulderScaleDeg = 6f;
    [Tooltip("Seconds at the right-hand end of the tempo and pause bars.")]
    public float tempoScaleS = 4f;
    public float pauseScaleS = 3f;

    [Tooltip("Share of the repetition that counts as a fault; must match VALGUS_FAULT_FRACTION in rep_engine.py.")]
    public float valgusGateFraction = 0.30f;

    [Tooltip("Inward-movement share above which a rep reads 'Mostly tracking well'.")]
    public float wobbleFraction = 0.05f;

    [Tooltip("Knee-angle difference treated as even, in degrees. Drawn as the dashed " +
             "line on the left/right trace.")]
    public float symmetryEvenDeg = 3f;

    [Tooltip("Full scale of the knee-tracking graph, in millimetres.")]
    public float valgusScaleMm = 60f;

    UIDocument _doc;
    VisualElement _depthTicks, _kneeTicks, _symTicks, _shTicks, _shBand;
    Label _shBandLabel, _shZero, _kneeZero;
    VisualElement _root, _sheet, _verdict, _depthChart, _depthBand, _kneeChart,
                  _shChart, _symChart, _kneeIcon, _shIcon, _symIcon, _styleIcon,
                  _keyChart, _valgusCue,
                  _tempoDown, _tempoUp, _pauseFill, _tempoAxis, _pauseAxis;
    Label _title, _sub, _vTitle, _vBody,
          _depthState, _depthNum, _kneeState, _kneeNum, _symState, _symNum,
          _shState, _shNum, _styleState, _styleNum, _tempoState, _tempoDownVal, _tempoUpVal,
          _pauseState, _pauseVal, _kneeHoldNum, _kneeWhen,
          _cueTitle, _cueBody, _kneeXLabel, _depthXLabel, _symXLabel, _shXLabel,
          _depthBandLabel;
    PaintElement _depthPaint, _kneePaint, _shPaint, _symPaint,
                 _kneeIconPaint, _shIconPaint, _symIconPaint, _styleIconPaint, _keyPaint;
    float _phase1 = -1f, _phase2 = -1f;
    float _repSeconds = 0f;

    int _shown = -1;
    /// Whether the last draw came from the set summary rather than from the live stream.
    bool _wasFromSet;
    Button _btnDone, _btnEnd, _btnClose;
    VisualElement _phaseKey;
    static readonly string[] TraceKeys = { "depth", "knee", "sym", "sh" };

    /// Show one measurement's pane and mark its card as pressed.
    void Select(string key)
    {
        if (_root == null) return;
        _root.Query<Button>(className: "mcard").ForEach(b => b.EnableInClassList("on", b.name == "mc-" + key));
        _root.Query<VisualElement>(className: "pane").ForEach(p => p.EnableInClassList("hidden", p.name != "pane-" + key));
        _phaseKey?.EnableInClassList("hidden", System.Array.IndexOf(TraceKeys, key) < 0);
    }

    /// Set a card's status pill: cls is good / warn / fault / neutral.
    void Pill(string key, string cls, string text)
    {
        var l = _root?.Q<Label>(key + "-pill");
        if (l == null) return;
        l.text = text;
        foreach (var c in new[] { "good", "warn", "fault", "neutral" }) l.EnableInClassList("pill-" + c, c == cls);
    }

    /// Set the big number at the top of a pane.
    void Big(string key, string text)
    {
        var l = _root?.Q<Label>(key + "-big");
        if (l != null) l.text = text;
    }

    void OnEnable()
    {
        _doc = GetComponent<UIDocument>();
        if (receiver == null) receiver = FindAnyObjectByType<PoseUdpReceiver>();
        if (flow == null) flow = FindAnyObjectByType<ScreenFlowController>();
        _root = null;
        _shown = -1;
        _wasFromSet = false;
    }

    T Get<T>(string n) where T : VisualElement
    {
        var e = _root.Q<T>(n);
        if (e == null) Debug.LogWarning($"[PostRepUI] no element named '{n}' in the UXML.");
        return e;
    }

    bool Bind()
    {
        var root = _doc != null ? _doc.rootVisualElement : null;
        if (root == null) return false;
        if (root == _root) return true;
        _root = root;
        _root.style.flexGrow = 1;
        for (int i = 0; i < _root.childCount; i++)
        {
            var c = _root[i];
            c.style.position = Position.Absolute;
            c.style.left = 0; c.style.top = 0; c.style.right = 0; c.style.bottom = 0;
        }

        _sheet      = Get<VisualElement>("sheet");
        _title      = Get<Label>("rep-title");
        _sub        = Get<Label>("rep-sub");
        _verdict    = Get<VisualElement>("verdict-card");
        _vTitle     = Get<Label>("verdict-title");
        _vBody      = Get<Label>("verdict-body");
        _depthState = Get<Label>("depth-state");
        _depthNum   = Get<Label>("depth-num");
        _depthChart = Get<VisualElement>("depth-chart");
        _depthBand  = Get<VisualElement>("depth-band");
        _depthXLabel = Get<Label>("depth-xlabel");
        _depthBandLabel = Get<Label>("depth-band-label");
        _depthTicks = Get<VisualElement>("depth-yticks");
        _kneeTicks  = Get<VisualElement>("knee-yticks");
        _symTicks   = Get<VisualElement>("sym-yticks");
        _shTicks    = Get<VisualElement>("sh-yticks");
        _symXLabel  = Get<Label>("sym-xlabel");
        _shXLabel   = Get<Label>("sh-xlabel");
        _shBand     = Get<VisualElement>("sh-band");
        _shBandLabel = Get<Label>("sh-band-label");
        _shZero = _kneeZero = null;
        _kneeState  = Get<Label>("knee-state");
        _kneeNum    = Get<Label>("knee-num");
        _kneeChart  = Get<VisualElement>("knee-chart");
        _kneeIcon   = Get<VisualElement>("knee-icon");
        _shIcon     = Get<VisualElement>("sh-icon");
        _symIcon    = Get<VisualElement>("sym-icon");
        _styleIcon  = Get<VisualElement>("style-icon");
        _keyChart   = Get<VisualElement>("phase-key-chart");
        _valgusCue  = Get<VisualElement>("valgus-cue");
        _cueTitle   = Get<Label>("valgus-cue-title");
        _cueBody    = Get<Label>("valgus-cue-body");
        _kneeXLabel = Get<Label>("knee-xlabel");
        _kneeHoldNum = Get<Label>("knee-hold-num");
        _kneeWhen    = Get<Label>("knee-when");
        _symState   = Get<Label>("sym-state");
        _symNum     = Get<Label>("sym-num");
        _symChart   = Get<VisualElement>("sym-chart");
        _shState    = Get<Label>("sh-state");
        _shNum      = Get<Label>("sh-num");
        _shChart    = Get<VisualElement>("sh-chart");
        _styleState = Get<Label>("style-state");
        _styleNum   = Get<Label>("style-num");
        _tempoState = Get<Label>("tempo-state");
        _tempoDown  = Get<VisualElement>("tempo-down");
        _tempoUp    = Get<VisualElement>("tempo-up");
        _tempoDownVal = Get<Label>("tempo-down-val");
        _tempoUpVal   = Get<Label>("tempo-up-val");
        _tempoAxis  = Get<VisualElement>("tempo-axis");
        _pauseState = Get<Label>("pause-state");
        _pauseVal   = Get<Label>("pause-fill-val");
        _pauseFill  = Get<VisualElement>("pause-fill");
        _pauseAxis  = Get<VisualElement>("pause-axis");

        _root.Query<Button>(className: "mcard").ForEach(b =>
        {
            string key = b.name.Substring(3);
            b.Query<VisualElement>().ForEach(c => { if (c != b) c.pickingMode = PickingMode.Ignore; });
            b.clicked += () => Select(key);
        });
        _phaseKey = _root.Q<VisualElement>("phase-key");

        _btnDone = _root.Q<Button>("btn-done");
        if (_btnDone != null) _btnDone.clicked += () => { if (flow != null) flow.DismissPostRep(); };
        _btnEnd = _root.Q<Button>("btn-end");
        if (_btnEnd != null) _btnEnd.clicked += () => { if (flow != null) flow.EndSet(); };
        _btnClose = _root.Q<Button>("btn-close");
        if (_btnClose != null) _btnClose.clicked += () => { if (flow != null) flow.BackToSet(); };

        _depthPaint = AddPaint(_depthChart);
        _kneePaint  = AddPaint(_kneeChart);
        _shPaint    = AddPaint(_shChart);
        _symPaint   = AddPaint(_symChart);
        _kneeIconPaint  = AddPaint(_kneeIcon);
        _shIconPaint    = AddPaint(_shIcon);
        _symIconPaint   = AddPaint(_symIcon);
        _styleIconPaint = AddPaint(_styleIcon);
        _keyPaint       = AddPaint(_keyChart);
        DrawKneeIcon();
        DrawShoulderIcon();
        DrawSymmetryIcon();
        DrawStyleIcon();
        DrawPhaseKey();

        Debug.Log("[PostRepUI] bound to the visual tree.");
        return true;
    }

    static PaintElement AddPaint(VisualElement host)
    {
        if (host == null) return null;
        var p = new PaintElement();
        p.style.position = Position.Absolute;
        p.style.left = 0; p.style.top = 0; p.style.right = 0; p.style.bottom = 0;
        host.Add(p);
        return p;
    }

    void Update()
    {
        if (!Bind()) return;
        if (_sheet != null) _sheet.EnableInClassList("no-numbers", !SessionSettings.ShowNumbers);

        bool fromSet = flow != null && flow.ReviewingFromSet;
        if (fromSet != _wasFromSet) { _wasFromSet = fromSet; _shown = -1; }
        _btnDone?.EnableInClassList("hidden", fromSet);
        _btnEnd?.EnableInClassList("hidden", fromSet);
        _btnClose?.EnableInClassList("hidden", !fromSet);

        if (fromSet)
        {
            JSONNode chosen = flow.RepUnderReview;
            if (chosen == null) return;
            if (flow.RepUnderReviewIndex == _shown) return;
            _shown = flow.RepUnderReviewIndex;
            Draw(chosen);
            return;
        }

        if (receiver == null || receiver.LastRep == null) return;
        if (receiver.RepSequence == _shown) return;
        _shown = receiver.RepSequence;
        Draw(receiver.LastRep);
    }

    void Draw(JSONNode r)
    {
        float repS = F(r["descent_s"]) + F(r["bottom_dwell_s"]) + F(r["ascent_s"]);
        _repSeconds = repS;
        _phase1 = repS > 0f ? F(r["t_bottom_s"]) / repS : -1f;
        _phase2 = repS > 0f ? F(r["t_ascent_s"]) / repS : -1f;
        DrawPhaseKey();

        string target = r["target_depth"].Value;
        string did = r["variation"].Value;
        string met = r["depth_met"].Value;
        bool depthOk = met == "True" || met == "true";

        if (_title != null) _title.text = string.Format(PostRepCopy.RepTitle, r["rep"].Value);
        if (_sub != null)
            _sub.text = string.Format(PostRepCopy.Subtitle,
                                      PostRepCopy.DepthWord(target),
                                      PostRepCopy.DepthWord(did));

        JSONNode cues = r["cues"];
        bool clean = r["faults"] == null || r["faults"].Count == 0;
        if (_vTitle != null)
            _vTitle.text = clean ? PostRepCopy.GoodRep : Title(FirstFault(r));
        if (_vBody != null)
            _vBody.text = (cues != null && cues.Count > 0) ? cues[0].Value : "";
        _verdict?.EnableInClassList("ok", clean);
        _verdict?.EnableInClassList("warn", !clean && FirstFault(r) == "depth_unmeasured");

        float margin = F(r["depth_margin_mm"]);
        bool deeper = met == "deeper";
        bool unmeasured = HasFault(r, "depth_unmeasured");
        Set(_depthState, string.Format(PostRepCopy.DepthOv, PostRepCopy.DepthWord(target),
                                       PostRepCopy.DepthWord(did)), "");
        if (unmeasured) Pill("depth", "neutral", PostRepCopy.PillUnmeasured);
        else if (depthOk) Pill("depth", "good", PostRepCopy.PillOnTarget);
        else if (deeper) Pill("depth", "warn", PostRepCopy.PillDeeper);
        else Pill("depth", "fault", PostRepCopy.PillShallow);
        Big("depth", string.Format(PostRepCopy.DepthBig, margin));
        if (_depthNum != null)
            _depthNum.text = string.Format(PostRepCopy.DepthBigCap, F(r["knee_at_depth"]));
        DrawTrace(r["trace"], r);

        float devMm = F(r["valgus_dev_mm"]), limitMm = F(r["valgus_limit_mm"]);
        string ff = FirstFault(r);
        bool kneeBad = HasFault(r, "valgus");
        float hold = F(r["valgus_frac"]);
        Set(_kneeState, kneeBad ? PostRepCopy.FaultValgus
                      : hold >= wobbleFraction ? PostRepCopy.KneeMostly
                                               : PostRepCopy.KneeGood,
            kneeBad ? "state-warn" : "");
        Pill("knee", kneeBad ? "fault" : hold > 0f ? "warn" : "good",
             kneeBad ? PostRepCopy.PillSustained : hold > 0f ? PostRepCopy.PillBrief : PostRepCopy.PillOnTarget);
        Big("knee", string.Format(PostRepCopy.KneeBig, -devMm));
        if (_kneeNum != null) _kneeNum.text = PostRepCopy.KneeBigCap;
        DrawKneeChart(r["valgus_traj"], limitMm);

        bool anyCave = hold > 0f;
        _valgusCue?.EnableInClassList("cue-bad", kneeBad);
        _valgusCue?.EnableInClassList("cue-warn", !kneeBad && anyCave);
        if (_cueTitle != null)
            _cueTitle.text = kneeBad ? PostRepCopy.CueBadTitle
                           : anyCave ? PostRepCopy.CueBriefTitle
                                     : PostRepCopy.CueOkTitle;
        if (_cueBody != null)
            _cueBody.text = kneeBad ? PostRepCopy.CueBadBody
                          : anyCave ? PostRepCopy.CueBriefBody
                                    : PostRepCopy.CueOkBody;
        if (_kneeHoldNum != null)
            _kneeHoldNum.text = anyCave ? string.Format(PostRepCopy.CueHoldOne, hold) : "";
        if (_kneeWhen != null)
            _kneeWhen.text = anyCave
                ? string.Format(PostRepCopy.CueWhen, F(r["valgus_s"]), PhaseAt(F(r["valgus_t"])))
                : "";

        float sym = F(r["symmetry_deg"]);
        Report(_symState, PostRepCopy.SymHeading);
        float symSigned = F(r["sym_signed_deg"]);
        string symSide = Mathf.Abs(symSigned) < symmetryEvenDeg ? PostRepCopy.SymEvenSide
                       : symSigned > 0f ? PostRepCopy.SymSideR : PostRepCopy.SymSideL;
        Pill("sym", "neutral", PostRepCopy.PillReported);
        Big("sym", string.Format(PostRepCopy.DegBig, sym));
        if (_symNum != null) _symNum.text = string.Format(PostRepCopy.SymBigCap, symSide);
        if (_symXLabel != null) _symXLabel.text = PostRepCopy.ChartXLabel;
        DrawTraj(_symPaint, _symTicks, r["sym_signed_traj"], symmetryScaleDeg * 0.4f, 0f);

        float tilt = F(r["shoulder_tilt_deg"]);
        Report(_shState, PostRepCopy.ShHeading);
        string shSide = Mathf.Abs(tilt) < 0.5f ? PostRepCopy.ShNeither
                      : tilt > 0f ? PostRepCopy.ShLeft : PostRepCopy.ShRight;
        Pill("sh", "neutral", PostRepCopy.PillReported);
        Big("sh", string.Format(PostRepCopy.DegBig, Mathf.Abs(tilt)));
        if (_shNum != null) _shNum.text = string.Format(PostRepCopy.ShBigCap, shSide);
        if (_shXLabel != null) _shXLabel.text = PostRepCopy.ChartXLabel;
        DrawTraj(_shPaint, _shTicks, r["shoulder_tilt_traj"], shoulderScaleDeg * 0.4f, 0f,
                 negate: true, band: _shBand, bandLabel: _shBandLabel,
                 bandAbs: F(r["shoulder_even_deg"]),
                 bandText: string.Format(PostRepCopy.ShBand, F(r["shoulder_even_deg"])),
                 zeroNote: _shZero, zeroText: PostRepCopy.ShZero);

        string dom = r["dominance"].Value;
        if (_styleState != null)
        {
            _styleState.text = StyleWord(dom);
            _styleState.RemoveFromClassList("state-warn");
            _styleState.AddToClassList("state-neutral");
        }
        Pill("style", "neutral", PostRepCopy.PillReported);
        Big("style", StyleWord(dom));
        if (_styleNum != null) _styleNum.text = string.Format(PostRepCopy.StyleBigCap, F(r["trunk_tibia_deg"]));

        float down = F(r["descent_s"]), up = F(r["ascent_s"]), dwell = F(r["bottom_dwell_s"]);
        if (_tempoState != null) _tempoState.text = string.Format(PostRepCopy.TempoNum, down, up);
        Pill("tempo", "neutral", PostRepCopy.PillReported);
        if (_tempoDownVal != null) _tempoDownVal.text = string.Format(PostRepCopy.BarSeconds, down);
        if (_tempoUpVal != null) _tempoUpVal.text = string.Format(PostRepCopy.BarSeconds, up);
        Fill(_tempoDown, down / tempoScaleS);
        Fill(_tempoUp, up / tempoScaleS);
        BarAxis.Build(_tempoAxis, tempoScaleS);

        if (_pauseState != null)
            _pauseState.text = dwell < 0.15f ? PostRepCopy.PauseNone : dwell < 0.8f ? PostRepCopy.PauseBrief : PostRepCopy.PauseHeld;
        Pill("pause", "neutral", PostRepCopy.PillReported);
        if (_pauseVal != null) _pauseVal.text = string.Format(PostRepCopy.BarSeconds, dwell);
        BarAxis.Build(_pauseAxis, pauseScaleS);

        Select(kneeBad ? "knee" : "depth");
        Fill(_pauseFill, dwell / pauseScaleS);
    }

    void DrawTrace(JSONNode trace, JSONNode rep)
    {
        if (_depthPaint == null) return;
        _depthPaint.Clear();
        if (trace == null || trace.IsNull || trace.Count < 2) return;

        if (_depthXLabel != null) _depthXLabel.text = PostRepCopy.ChartXLabel;

        int n = trace.Count;
        var seen = new List<float>(n + 2);
        for (int i = 0; i < n; i++) seen.Add(trace[i].AsFloat);
        JSONNode tgt = BandOf(rep);
        if (tgt != null)
        {
            seen.Add(tgt["hi"].AsFloat);
            if (tgt["lo"] != null && !tgt["lo"].IsNull) seen.Add(tgt["lo"].AsFloat);
        }
        Bounds(seen, false, out float dlo, out float dhi, out int dticks);
        Axis(_depthTicks, _depthPaint, dlo, dhi, dticks);
        DrawPhaseLines(_depthPaint);

        var pts = new List<Vector2>(n);
        for (int i = 0; i < n; i++)
            pts.Add(new Vector2(n == 1 ? 0f : (float)i / (n - 1),
                                YN(trace[i].AsFloat, dlo, dhi)));
        _depthPaint.Add(new PaintElement.Path
        {
            points = pts.ToArray(),
            color = Trace,
            width = 2.5f
        });

        if (_depthBand != null)
        {
            JSONNode tg = BandOf(rep);
            if (tg != null)
            {
                bool open = tg["lo"] == null || tg["lo"].IsNull;
                float a = YN(tg["hi"].AsFloat, dlo, dhi);
                float b = open ? 1f : YN(tg["lo"].AsFloat, dlo, dhi);
                _depthBand.style.top = Length.Percent(a * 100f);
                _depthBand.style.height = Length.Percent(Mathf.Max(b - a, 0f) * 100f);
                if (_depthBandLabel != null) _depthBandLabel.text = PostRepCopy.DepthBand;
            }
        }
    }

    /// Front view of both legs with a dashed hip-to-ankle line.

    static readonly Color32 IconGrey = new Color32(0x75, 0x80, 0x8c, 255);
    static readonly Color32 IconBlue = new Color32(0x7f, 0xb4, 0xf2, 255);
    static readonly Color32 Trace    = new Color32(0x7f, 0xb4, 0xf2, 255);
    static readonly Color32 RefLine  = new Color32(0x5d, 0x67, 0x72, 255);
    static readonly Color32 PhaseGrey = new Color32(0x3a, 0x45, 0x52, 255);
    static readonly Color32 IconWarn = new Color32(0xe0, 0x7a, 0x1c, 255);
    static readonly Color32 IconGap  = new Color32(0xc4, 0x3c, 0x2c, 255);

    static Vector2[] Ring(Vector2 c, float rx, float ry, int n = 14)
    {
        var p = new Vector2[n + 1];
        for (int i = 0; i <= n; i++)
        {
            float a = i * 2f * Mathf.PI / n;
            p[i] = new Vector2(c.x + rx * Mathf.Cos(a), c.y + ry * Mathf.Sin(a));
        }
        return p;
    }

    void Line(PaintElement p, Color32 c, float w, bool dashed, params Vector2[] pts)
    {
        p?.Add(new PaintElement.Path { points = pts, color = c, width = w, dashed = dashed });
    }

    /// Two legs from the front with the gap between the knees marked, and arrows showing it closing.
    void DrawKneeIcon()
    {
        if (_kneeIconPaint == null) return;
        _kneeIconPaint.Clear();
        var hipL = new Vector2(0.28f, 0.10f); var ankL = new Vector2(0.22f, 0.94f);
        var hipR = new Vector2(0.72f, 0.10f); var ankR = new Vector2(0.78f, 0.94f);
        var kneeL = new Vector2(0.41f, 0.52f); var kneeR = new Vector2(0.59f, 0.52f);
        Line(_kneeIconPaint, IconBlue, 3f, false, hipL, kneeL, ankL);
        Line(_kneeIconPaint, IconBlue, 3f, false, hipR, kneeR, ankR);
        Line(_kneeIconPaint, IconGrey, 1.4f, true,
             new Vector2(kneeL.x, 0.52f), new Vector2(kneeR.x, 0.52f));
        Arrow(_kneeIconPaint, new Vector2(0.30f, 0.36f), new Vector2(0.44f, 0.36f), IconWarn);
        Arrow(_kneeIconPaint, new Vector2(0.70f, 0.36f), new Vector2(0.56f, 0.36f), IconWarn);
    }

    /// A short line with a head, for showing which way something moved.
    void Arrow(PaintElement p, Vector2 from, Vector2 to, Color32 c)
    {
        Line(p, c, 2.5f, false, from, to);
        Vector2 d = (to - from).normalized, n = new Vector2(-d.y, d.x);
        Line(p, c, 2.5f, false, to - d * 0.07f + n * 0.05f, to, to - d * 0.07f - n * 0.05f);
    }

    /// Front view of both legs with one knee bent further.
    void DrawSymmetryIcon()
    {
        if (_symIconPaint == null) return;
        _symIconPaint.Clear();
        var hipL = new Vector2(0.34f, 0.14f); var ankL = new Vector2(0.30f, 0.94f);
        var hipR = new Vector2(0.66f, 0.14f); var ankR = new Vector2(0.70f, 0.94f);
        var kneeL = new Vector2(0.24f, 0.46f);
        var kneeR = new Vector2(0.76f, 0.62f);
        Line(_symIconPaint, IconBlue, 2.5f, false, hipL, hipR);
        Line(_symIconPaint, IconBlue, 3f, false, hipL, kneeL, ankL);
        Line(_symIconPaint, IconBlue, 3f, false, hipR, kneeR, ankR);
        Line(_symIconPaint, IconGrey, 1.4f, true,
             new Vector2(0.10f, 0.46f), new Vector2(0.90f, 0.46f));
        Line(_symIconPaint, IconGap, 2.5f, false,
             new Vector2(0.80f, 0.46f), new Vector2(0.80f, 0.62f));
    }

    /// Head, torso and a shoulder line that is off horizontal.
    void DrawShoulderIcon()
    {
        if (_shIconPaint == null) return;
        _shIconPaint.Clear();
        var shL = new Vector2(0.22f, 0.40f); var shR = new Vector2(0.78f, 0.62f);
        Line(_shIconPaint, IconGrey, 1.4f, true,
             new Vector2(0.12f, 0.51f), new Vector2(0.88f, 0.51f));
        Line(_shIconPaint, IconBlue, 2.5f, false, Ring(new Vector2(0.50f, 0.20f), 0.09f, 0.13f));
        Line(_shIconPaint, IconBlue, 3.5f, false, shL, shR);
        Line(_shIconPaint, IconBlue, 2.5f, false,
             new Vector2(0.50f, 0.51f), new Vector2(0.50f, 0.90f));
        Line(_shIconPaint, IconGap, 2.5f, false, new Vector2(0.78f, 0.51f), shR);
    }

    /// Front-view squat pictogram.
    void DrawStyleIcon()
    {
        if (_styleIconPaint == null) return;
        _styleIconPaint.Clear();

        var head  = new Vector2(0.50f, 0.14f);
        var shL   = new Vector2(0.37f, 0.34f);
        var shR   = new Vector2(0.63f, 0.34f);
        var hipL  = new Vector2(0.42f, 0.60f);
        var hipR  = new Vector2(0.58f, 0.60f);
        var kneeL = new Vector2(0.26f, 0.74f);
        var kneeR = new Vector2(0.74f, 0.74f);
        var ankL  = new Vector2(0.22f, 0.94f);
        var ankR  = new Vector2(0.78f, 0.94f);

        Line(_styleIconPaint, IconGrey, 3f, false,
             new Vector2(0.10f, 0.30f), new Vector2(0.90f, 0.30f));
        Line(_styleIconPaint, IconGrey, 3f, false,
             new Vector2(0.12f, 0.22f), new Vector2(0.12f, 0.38f));
        Line(_styleIconPaint, IconGrey, 3f, false,
             new Vector2(0.88f, 0.22f), new Vector2(0.88f, 0.38f));

        Line(_styleIconPaint, IconBlue, 2.5f, false, Ring(head, 0.085f, 0.115f));
        Line(_styleIconPaint, IconBlue, 3.5f, false, shL, shR);
        Line(_styleIconPaint, IconBlue, 3f, false, shL, new Vector2(0.26f, 0.44f),
             new Vector2(0.30f, 0.30f));
        Line(_styleIconPaint, IconBlue, 3f, false, shR, new Vector2(0.74f, 0.44f),
             new Vector2(0.70f, 0.30f));
        Line(_styleIconPaint, IconWarn, 3.5f, false,
             new Vector2(0.50f, 0.34f), new Vector2(0.50f, 0.60f));
        Line(_styleIconPaint, IconBlue, 3f, false, hipL, hipR);
        Line(_styleIconPaint, IconWarn, 3f, false, hipL, kneeL, ankL);
        Line(_styleIconPaint, IconWarn, 3f, false, hipR, kneeR, ankR);
    }

    /// Change in the gap between the knees, against the athlete's own standing gap.
    void DrawKneeChart(JSONNode traj, float limitMm)
    {
        if (_kneePaint == null) return;
        _kneePaint.Clear();
        if (traj == null || traj.IsNull || traj.Count < 2) return;

        var seen = new List<float>(traj.Count + 1);
        for (int i = 0; i < traj.Count; i++) seen.Add(traj[i][1].AsFloat);
        seen.Add(limitMm * 1.4f);
        Bounds(seen, true, out float lo, out float hi, out int ticks);
        float Y(float mm) => YN(mm, lo, hi);
        Axis(_kneeTicks, _kneePaint, lo, hi, ticks);

        float t0 = traj[0][0].AsFloat, t1 = traj[traj.Count - 1][0].AsFloat;
        if (_kneeXLabel != null) _kneeXLabel.text = PostRepCopy.ChartXLabel;

        DrawPhaseLines(_kneePaint);
        float yZero = Y(0f);
        Line(_kneePaint, RefLine, 1.5f, false,
             new Vector2(0.06f, yZero), new Vector2(0.94f, yZero));
        if (_kneeZero != null)
        {
            _kneeZero.text = PostRepCopy.KneeZero;
            _kneeZero.style.top = Length.Percent(yZero * 100f);
        }
        if (limitMm > lo && limitMm < hi)
            Line(_kneePaint, new Color32(0xe0, 0x6a, 0x5a, 255), 1.5f, true,
                 new Vector2(0.06f, Y(limitMm)), new Vector2(0.94f, Y(limitMm)));

        float span = Mathf.Max(t1 - t0, 1e-3f);
        var pts = new List<Vector2>(traj.Count);
        for (int i = 0; i < traj.Count; i++)
            pts.Add(new Vector2(0.06f + 0.88f * Mathf.Clamp01((traj[i][0].AsFloat - t0) / span),
                                Y(traj[i][1].AsFloat)));
        _kneePaint.Add(new PaintElement.Path
        {
            points = pts.ToArray(), color = IconWarn, width = 2.5f,
            fillColor = new Color(0.88f, 0.48f, 0.11f, 0.13f), fillTo = yZero
        });
    }

    /// The phase a moment in the repetition fell in.
    string PhaseAt(float t)
    {
        if (_repSeconds <= 0f) return PostRepCopy.PhaseDescent;
        float f = t / _repSeconds;
        if (f < _phase1) return PostRepCopy.PhaseDescent;
        if (f < _phase2) return PostRepCopy.PhaseBottom;
        return PostRepCopy.PhaseAscent;
    }

    /// Legend for the phase dividers on the charts.
    void DrawPhaseKey()
    {
        if (_keyPaint == null) return;
        _keyPaint.Clear();
        bool hasBottom = HasLine(_phase1) && HasLine(_phase2) && _phase2 - _phase1 > 0.02f;
        _root?.Q<Label>("key-bottom")?.EnableInClassList("hidden", !hasBottom);
        var keyNote = _root?.Q<Label>("phase-key-note");
        if (keyNote != null) keyNote.text = hasBottom ? PostRepCopy.PhaseKey3 : PostRepCopy.PhaseKey2;
        var grey = PhaseGrey;
        foreach (float x in hasBottom ? new[] { 1f / 3f, 2f / 3f } : new[] { 0.5f })
            _keyPaint.Add(new PaintElement.Path
            {
                points = new[] { new Vector2(x, 0.05f), new Vector2(x, 0.95f) },
                color = grey, width = 1.5f, dashed = true
            });
        _keyPaint.Add(new PaintElement.Path
        {
            points = new[] { new Vector2(0.01f, 0.55f), new Vector2(0.99f, 0.55f) },
            color = grey, width = 1.4f, dashed = true
        });
    }

    /// Two faint verticals splitting a chart into descent, bottom and ascent.
    void DrawPhaseLines(PaintElement paint)
    {
        var grey = PhaseGrey;
        bool same = Mathf.Abs(_phase2 - _phase1) <= 0.02f;
        foreach (float f in same ? new[] { _phase1 } : new[] { _phase1, _phase2 })
        {
            if (!HasLine(f)) continue;
            float x = 0.06f + 0.88f * f;
            paint.Add(new PaintElement.Path
            {
                points = new[] { new Vector2(x, 0.05f), new Vector2(x, 0.95f) },
                color = grey, width = 1.5f, dashed = true
            });
        }
    }

    static bool HasLine(float f) => f > 0.02f && f < 0.98f;

    /// Symmetric axis range around zero, at least `floorAbs` either side.
    void DrawTraj(PaintElement paint, VisualElement ticks, JSONNode traj,
                  float floorAbs, float refValue,
                  bool absolute = false, int series = 1, bool negate = false,
                  VisualElement band = null, Label bandLabel = null,
                  float bandAbs = float.NaN, string bandText = null,
                  Label zeroNote = null, string zeroText = null)
    {
        if (paint == null) return;
        paint.Clear();
        ticks?.Clear();
        if (band != null) band.style.display = DisplayStyle.None;
        if (zeroNote != null) zeroNote.style.display = DisplayStyle.None;
        if (traj == null || traj.IsNull || traj.Count < 2) return;

        var seen = new List<float> { floorAbs, -floorAbs, refValue };
        if (!float.IsNaN(bandAbs) && bandAbs > 0f) { seen.Add(bandAbs); seen.Add(-bandAbs); }
        for (int i = 0; i < traj.Count; i++)
            for (int k = 0; k < series; k++)
            {
                float v = negate ? -traj[i][1 + k].AsFloat : traj[i][1 + k].AsFloat;
                seen.Add(absolute ? Mathf.Abs(v) : v);
            }
        Bounds(seen, !absolute, out float lo, out float hi, out int nTicks);
        Axis(ticks, paint, lo, hi, nTicks);

        float Y(float raw)
        {
            float v = negate ? -raw : raw;
            return YN(absolute ? Mathf.Abs(v) : v, lo, hi);
        }
        if (band != null && !float.IsNaN(bandAbs) && bandAbs > 0f)
        {
            float top = YN(bandAbs, lo, hi), bot = YN(-bandAbs, lo, hi);
            band.style.display = DisplayStyle.Flex;
            band.style.top = Length.Percent(top * 100f);
            band.style.height = Length.Percent(Mathf.Max(bot - top, 0f) * 100f);
            if (bandLabel != null) bandLabel.text = bandText ?? "";
        }
        DrawPhaseLines(paint);
        float yRef = Y(refValue);
        if (zeroNote != null && !string.IsNullOrEmpty(zeroText))
        {
            zeroNote.style.display = DisplayStyle.Flex;
            zeroNote.text = zeroText;
            zeroNote.style.top = Length.Percent(yRef * 100f);
        }
        paint.Add(new PaintElement.Path
        {
            points = new[] { new Vector2(0.06f, yRef), new Vector2(0.94f, yRef) },
            color = RefLine, width = 1.5f
        });

        int n = traj.Count;
        float t0 = traj[0][0].AsFloat, t1 = traj[n - 1][0].AsFloat;
        float span = Mathf.Max(t1 - t0, 1e-3f);
        var colours = new[] { Trace,
                              new Color32(0xe0, 0x7a, 0x1c, 255) };
        for (int k = 0; k < series; k++)
        {
            var pts = new List<Vector2>(n);
            for (int i = 0; i < n; i++)
            {
                float x = 0.06f + 0.88f * Mathf.Clamp01((traj[i][0].AsFloat - t0) / span);
                pts.Add(new Vector2(x, Y(traj[i][1 + k].AsFloat)));
            }
            paint.Add(new PaintElement.Path
            {
                points = pts.ToArray(), color = colours[k % 2], width = 2.5f
            });
        }
    }

    static readonly Color32 GridLine = new Color32(0x26, 0x30, 0x3c, 255);

    static float YN(float v, float lo, float hi) =>
        1f - Mathf.Clamp01(Mathf.InverseLerp(lo, hi, v));

    /// The depth target band for a rep.
    JSONNode BandOf(JSONNode rep)
    {
        JSONNode b = rep != null ? rep["depth_band"] : null;
        if (b != null && !b.IsNull && b["hi"] != null && !b["hi"].IsNull) return b;
        if (receiver == null || receiver.Latest == null) return null;
        JSONNode st = receiver.Latest["state"];
        b = (st != null && !st.IsNull) ? st["depth_target"] : null;
        return (b != null && !b.IsNull && b["hi"] != null && !b["hi"].IsNull) ? b : null;
    }

    static float NiceStep(float raw)
    {
        if (raw <= 0f || float.IsNaN(raw) || float.IsInfinity(raw)) return 1f;
        float mag = Mathf.Pow(10f, Mathf.Floor(Mathf.Log10(raw)));
        float f = raw / mag;
        if (f <= 1f) return mag;
        if (f <= 2f) return 2f * mag;
        if (f <= 5f) return 5f * mag;
        return 10f * mag;
    }

    /// A rounded axis range covering `vals` with 3 to 6 gridlines.
    static void Bounds(List<float> vals, bool symmetric,
                       out float lo, out float hi, out int ticks)
    {
        lo = 0f; hi = 1f; ticks = 2;
        if (vals == null || vals.Count == 0) return;

        float min = float.MaxValue, max = float.MinValue;
        foreach (float v in vals)
        {
            if (float.IsNaN(v) || float.IsInfinity(v)) continue;
            if (v < min) min = v;
            if (v > max) max = v;
        }
        if (min > max) return;
        if (symmetric) { float m = Mathf.Max(Mathf.Abs(min), Mathf.Abs(max)); min = -m; max = m; }

        float range = max - min;
        if (range < 1e-6f) { range = Mathf.Max(Mathf.Abs(max), 1f); max = min + range; }
        max += range * 0.12f;
        min -= range * 0.12f;
        if (symmetric) { float m = Mathf.Max(Mathf.Abs(min), Mathf.Abs(max)); min = -m; max = m; }

        float step = NiceStep((max - min) / 3f);
        for (int guard = 0; guard < 8; guard++)
        {
            lo = Mathf.Floor(min / step) * step;
            hi = Mathf.Ceil(max / step) * step;
            ticks = Mathf.RoundToInt((hi - lo) / step) + 1;
            if (ticks > 6) { step *= 2f; continue; }
            if (ticks < 3) { step /= 2f; continue; }
            break;
        }
        ticks = Mathf.Clamp(ticks, 2, 7);
        if (hi - lo < 1e-6f) hi = lo + 1f;
    }

    /// Draws one gridline and label per tick.
    void Axis(VisualElement gutter, PaintElement paint, float lo, float hi, int ticks)
    {
        gutter?.Clear();
        if (paint == null) return;
        string fmt = (hi - lo) < 6f ? "0.0" : "0";
        for (int i = 0; i < ticks; i++)
        {
            float y = ticks == 1 ? 0.5f : (float)i / (ticks - 1);
            paint.Add(new PaintElement.Path
            {
                points = new[] { new Vector2(0f, y), new Vector2(1f, y) },
                color = GridLine, width = 1f
            });
            if (gutter == null) continue;
            var l = new Label((hi - (hi - lo) * y).ToString(fmt));
            l.AddToClassList("ry-tick");
            gutter.Add(l);
        }
    }

    static void Fill(VisualElement bar, float f)
    {
        if (bar != null) bar.style.width = Length.Percent(Mathf.Clamp01(f) * 100f);
    }

    /// A sentence stating a measurement.
    static void Report(Label l, string text)
    {
        if (l == null) return;
        l.text = text;
        l.EnableInClassList("state-warn", false);
        l.EnableInClassList("state-neutral", true);
    }

    static void Set(Label l, string text, string cls)
    {
        if (l == null) return;
        l.text = text;
        l.EnableInClassList("state-warn", cls == "state-warn");
        l.EnableInClassList("state-neutral", false);
    }

    static bool B(JSONNode n) => n != null && !n.IsNull && n.AsBool;

    /// A bool the engine sent, or `fallback` if that report predates the field.
    static bool Flag(JSONNode n, bool fallback) =>
        (n == null || n.IsNull) ? fallback : n.AsBool;

    static float F(JSONNode n) => (n == null || n.IsNull) ? 0f : n.AsFloat;

    /// True if `fault` appears anywhere in the rep's faults list.
    static bool HasFault(JSONNode r, string fault)
    {
        JSONNode f = r["faults"];
        if (f == null || f.IsNull) return false;
        for (int i = 0; i < f.Count; i++) if (f[i].Value == fault) return true;
        return false;
    }

    static string FirstFault(JSONNode r)
    {
        JSONNode f = r["faults"];
        return (f != null && !f.IsNull && f.Count > 0) ? f[0].Value : null;
    }

    static string Title(string fault)
    {
        switch (fault)
        {
            case "valgus": return PostRepCopy.FaultValgus;
            case "shallow": return PostRepCopy.DepthShallow;
            case "depth_unmeasured": return PostRepCopy.FaultUnmeasured;
            default: return PostRepCopy.FaultOther;
        }
    }

    static string StyleWord(string dominance)
    {
        if (string.IsNullOrEmpty(dominance)) return "—";
        if (dominance.Contains("hip")) return PostRepCopy.StyleHip;
        if (dominance.Contains("knee")) return PostRepCopy.StyleKnee;
        return PostRepCopy.StyleBalanced;
    }
}
