using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UIElements;
using SimpleJSON;

[RequireComponent(typeof(UIDocument))]
public class PostSetUIController : MonoBehaviour
{
    [Header("Wiring")]
    public PoseUdpReceiver receiver;
    public ScreenFlowController flow;

    [Header("Scales")]
    [Tooltip("Seconds at which the tempo bars are full. Same scale as the rep card.")]
    public float tempoScaleS = 4f;

    static readonly Color Grid   = new Color(1f, 1f, 1f, 0.07f);
    static readonly Color Line   = new Color(0.498f, 0.706f, 0.949f, 0.55f);
    static readonly Color Zero   = new Color32(0x5d, 0x67, 0x72, 255);
    static readonly Color Limit  = new Color32(0xf0, 0x7a, 0x68, 255);
    static readonly Color32 IconGrey = new Color32(0x75, 0x80, 0x8c, 255);
    static readonly Color32 IconBlue = new Color32(0x7f, 0xb4, 0xf2, 255);
    static readonly Color32 IconGap  = new Color32(0xc4, 0x3c, 0x2c, 255);

    UIDocument _doc;
    VisualElement _root, _sheet, _verdict;
    Label _title, _sub, _stamp, _vTitle, _vBody, _lgThresh;
    Label _depthState, _depthNum, _valgusState, _valgusNum;
    Label _symState, _symNum, _shState, _shNum;
    Label _tempoState, _repNavNote;
    VisualElement _depthPlot, _depthY, _depthX;
    VisualElement _valgusPlot, _valgusY, _valgusX;
    VisualElement _symPlot, _symY, _symX, _symIcon;
    VisualElement _shPlot, _shY, _shX, _shIcon;
    VisualElement _tempoDown, _tempoUp, _pauseTable, _repNav, _repNavTop;
    VisualElement _tempoAxis;
    Label _tempoDownVal, _tempoUpVal;

    int _drawnCount = -1;

    void OnEnable()
    {
        _doc = GetComponent<UIDocument>();
        if (receiver == null) receiver = FindAnyObjectByType<PoseUdpReceiver>();
        if (flow == null) flow = FindAnyObjectByType<ScreenFlowController>();
        _root = null;
        _drawnCount = -1;
    }

    /// Re-binds whenever the visual tree is replaced, which UI Toolkit does on every script reload, UXML save and screen enable.
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

        _sheet   = Get<VisualElement>("sheet");
        _verdict = Get<VisualElement>("verdict-card");
        _title   = Get<Label>("set-title");
        _sub     = Get<Label>("set-sub");
        _stamp   = Get<Label>("set-stamp");
        _vTitle  = Get<Label>("verdict-title");
        _vBody   = Get<Label>("verdict-body");
        _lgThresh = Get<Label>("lg-thresh");

        _depthState = Get<Label>("depth-state");
        _depthNum   = Get<Label>("depth-num");
        _depthPlot  = Get<VisualElement>("depth-plot");
        _depthY     = Get<VisualElement>("depth-yticks");
        _depthX     = Get<VisualElement>("depth-xticks");

        _valgusState = Get<Label>("valgus-state");
        _valgusNum   = Get<Label>("valgus-num");
        _valgusPlot  = Get<VisualElement>("valgus-plot");
        _valgusY     = Get<VisualElement>("valgus-yticks");
        _valgusX     = Get<VisualElement>("valgus-xticks");

        _symState = Get<Label>("sym-state");
        _symNum   = Get<Label>("sym-num");
        _symPlot  = Get<VisualElement>("sym-plot");
        _symY     = Get<VisualElement>("sym-yticks");
        _symX     = Get<VisualElement>("sym-xticks");
        _symIcon  = Get<VisualElement>("sym-icon");

        _shState = Get<Label>("sh-state");
        _shNum   = Get<Label>("sh-num");
        _shPlot  = Get<VisualElement>("sh-plot");
        _shY     = Get<VisualElement>("sh-yticks");
        _shX     = Get<VisualElement>("sh-xticks");
        _shIcon  = Get<VisualElement>("sh-icon");

        _tempoState = Get<Label>("tempo-state");
        _tempoDown  = Get<VisualElement>("tempo-down");
        _tempoUp    = Get<VisualElement>("tempo-up");
        _pauseTable = Get<VisualElement>("pause-table");
        _repNav     = Get<VisualElement>("rep-nav");
        _repNavNote = Get<Label>("rep-nav-note");
        _repNavTop  = Get<VisualElement>("rep-nav-top");
        _tempoDownVal = Get<Label>("tempo-down-val");
        _tempoUpVal   = Get<Label>("tempo-up-val");
        _tempoAxis  = Get<VisualElement>("tempo-axis");

        _root.Query<Button>(className: "mcard").ForEach(b =>
        {
            string key = b.name.Substring(3);
            b.Query<VisualElement>().ForEach(c => { if (c != b) c.pickingMode = PickingMode.Ignore; });
            b.clicked += () => Select(key);
        });
        Select("depth");

        var done = _root.Q<Button>("btn-done");
        if (done != null) done.clicked += () => { if (flow != null) flow.DismissPostSet(); };

        DrawSymIcon();
        DrawShIcon();

        Debug.Log("[PostSetUI] bound to the visual tree.");
        return true;
    }

    /// Show one measurement's pane and mark its card as pressed.
    void Select(string key)
    {
        if (_root == null) return;
        _root.Query<Button>(className: "mcard").ForEach(b => b.EnableInClassList("on", b.name == "mc-" + key));
        _root.Query<VisualElement>(className: "pane").ForEach(p => p.EnableInClassList("hidden", p.name != "pane-" + key));
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

    T Get<T>(string n) where T : VisualElement
    {
        var e = _root.Q<T>(n);
        if (e == null) Debug.LogWarning($"[PostSetUI] no element named '{n}' in the UXML.");
        return e;
    }

    void Update()
    {
        if (!Bind()) return;
        if (_sheet != null) _sheet.EnableInClassList("no-numbers", !SessionSettings.ShowNumbers);
        if (receiver == null) return;
        var reps = receiver.SetReps;
        if (reps.Count == 0) return;
        if (reps.Count == _drawnCount) return;
        _drawnCount = reps.Count;
        Draw(reps);
    }

    void Draw(List<JSONNode> reps)
    {
        int n = reps.Count;
        string target = reps[n - 1]["target_depth"].Value;
        int setNo = flow != null ? Mathf.Max(flow.SetIndex, 1) : 1;

        if (_title != null) _title.text = PostSetCopy.SetTitle;
        if (_sub != null)
            _sub.text = n == 1 ? string.Format(PostSetCopy.SetSubOne, setNo, Cap(target))
                               : string.Format(PostSetCopy.SetSubtitle, setNo, n, Cap(target));
        if (_stamp != null)
        {
            System.DateTime now = System.DateTime.Now;
            _stamp.text = now.ToString("ddd d MMM yyyy") + "\n" + now.ToString("HH:mm");
        }

        string[] repNos = new string[n];
        for (int i = 0; i < n; i++)
        {
            string v = reps[i]["rep"].Value;
            repNos[i] = string.IsNullOrEmpty(v) ? (i + 1).ToString() : v;
        }

        string scope = string.Format(PostSetCopy.ScopeSet, n);
        _root.Query<Label>(className: "scope").ForEach(l => l.text = scope);
        DrawVerdict(reps);
        DrawDepth(reps, repNos);
        DrawValgus(reps, repNos);
        DrawSymmetry(reps, repNos);
        DrawShoulders(reps, repNos);
        DrawTiming(reps, repNos);
        DrawRepNav(reps, repNos);
    }

    void DrawVerdict(List<JSONNode> reps)
    {
        int bad = 0;
        foreach (var r in reps) if (FaultCount(r) > 0) bad++;
        bool clean = bad == 0;
        _verdict?.EnableInClassList("ok", clean);
        _verdict?.EnableInClassList("warn", !clean);
        if (_vTitle != null)
            _vTitle.text = clean ? PostSetCopy.AllClean
                         : bad == 1 ? string.Format(PostSetCopy.OneFault, reps.Count)
                                    : string.Format(PostSetCopy.SomeFaults, bad, reps.Count);
        if (_vBody != null)
            _vBody.text = clean ? PostSetCopy.AllCleanBody : PostSetCopy.FaultsBody;
    }

    void DrawDepth(List<JSONNode> reps, string[] repNos)
    {
        int n = reps.Count;
        var vals = new float[n];
        var cls = new string[n];
        int onTarget = 0, measured = 0;
        float sum = 0f;

        for (int i = 0; i < n; i++)
        {
            JSONNode r = reps[i];
            string met = r["depth_met"].Value;
            bool ok = met == "True" || met == "true";
            bool deeper = met == "deeper";
            bool unmeasured = Has(r, "depth_unmeasured");
            if (ok) onTarget++;

            vals[i] = Num(r["depth_margin_mm"], out float m) && !unmeasured ? m : float.NaN;
            if (!float.IsNaN(vals[i])) { sum += vals[i]; measured++; }
            cls[i] = unmeasured ? "dot-none" : ok ? "dot-good" : deeper ? "dot-warn" : "dot-bad";
        }

        Set(_depthState, onTarget == n ? PostSetCopy.DepthAll
                       : string.Format(PostSetCopy.DepthOnTarget, onTarget, n),
            onTarget == n ? "" : "state-warn");
        if (_depthNum != null)
            _depthNum.text = measured == 0 ? PostSetCopy.Unmeasured
                           : string.Format(PostSetCopy.DepthNum, sum / measured);
        bool anyShallow = false;
        foreach (string c in cls) if (c == "dot-bad") anyShallow = true;
        if (onTarget == n) Pill("depth", "good", PostSetCopy.PillOnTarget);
        else Pill("depth", anyShallow ? "fault" : "warn", string.Format(PostSetCopy.PillOffTarget, n - onTarget));
        Big("depth", string.Format(PostSetCopy.CountBig, onTarget, n));

        bool hasBand = false, openLo = false; float bandLo = 0f, bandHi = 0f;
        JSONNode dt = null;
        for (int i = 0; i < n && dt == null; i++)
        {
            JSONNode b = reps[i]["depth_band"];
            if (b != null && !b.IsNull && b["hi"] != null && !b["hi"].IsNull) dt = b;
        }
        if (dt == null && receiver != null && receiver.Latest != null)
        {
            JSONNode st = receiver.Latest["state"];
            if (st != null && !st.IsNull) dt = st["depth_target"];
        }
        if (dt != null && !dt.IsNull && Num(dt["hi"], out float bh))
        {
            hasBand = true; bandHi = bh; bandLo = bh;
            if (Num(dt["lo"], out float bl))
            { bandLo = Mathf.Min(bl, bh); bandHi = Mathf.Max(bl, bh); }
            else openLo = true;
        }

        var extra = new List<float>();
        if (hasBand) { extra.Add(bandHi); if (!openLo) extra.Add(bandLo); }
        Plot(_depthPlot, _depthY, _depthX, vals, cls, repNos, extra, true, false,
             hasBand, bandLo, bandHi, false, 0f, false, openLo);
    }

    void DrawValgus(List<JSONNode> reps, string[] repNos)
    {
        int n = reps.Count;
        var vals = new float[n];
        var cls = new string[n];
        int caved = 0, measured = 0, closed = 0;
        float closedSum = 0f, signedSum = 0f, limit = float.NaN;

        for (int i = 0; i < n; i++)
        {
            JSONNode r = reps[i];
            bool bad = Has(r, "valgus");
            if (bad) caved++;
            bool brief = !bad && Num(r["valgus_frac"], out float f) && f > 0f;

            vals[i] = Num(r["valgus_dev_mm"], out float dev) ? -dev : float.NaN;
            if (!float.IsNaN(vals[i])) { measured++; signedSum += vals[i]; if (dev > 0f) { closedSum += dev; closed++; } }
            cls[i] = float.IsNaN(vals[i]) ? "dot-none"
                   : bad ? "dot-bad" : brief ? "dot-warn" : "dot-good";

            if (float.IsNaN(limit) && Num(r["valgus_limit_mm"], out float lm))
                limit = Mathf.Abs(lm);
        }

        Set(_valgusState, caved == 0 ? PostSetCopy.ValgusNone
                        : string.Format(PostSetCopy.ValgusSome, caved, n),
            caved == 0 ? "" : "state-warn");
        if (_valgusNum != null)
            _valgusNum.text = measured == 0 ? PostSetCopy.Unmeasured : PostSetCopy.ValgusBigCap;
        bool anyBrief = false;
        foreach (string c in cls) if (c == "dot-warn") anyBrief = true;
        if (caved > 0)
        {
            var flagged = new List<string>();
            for (int i = 0; i < n; i++) if (cls[i] == "dot-bad") flagged.Add(string.Format(PostSetCopy.RepList, repNos[i]));
            Pill("valgus", "fault", caved <= 2 ? string.Join(", ", flagged) : string.Format(PostSetCopy.PillFlagged, caved));
        }
        else if (anyBrief) Pill("valgus", "warn", PostSetCopy.PillBrief);
        else Pill("valgus", "good", PostSetCopy.PillOnTarget);
        Big("valgus", measured == 0 ? "-" : string.Format(PostSetCopy.ValgusBig, signedSum / measured));
        if (_lgThresh != null && !float.IsNaN(limit))
            _lgThresh.text = string.Format(PostSetCopy.ValgusLegend, limit);

        var extra = new List<float>();
        if (!float.IsNaN(limit)) extra.Add(-limit);
        Plot(_valgusPlot, _valgusY, _valgusX, vals, cls, repNos, extra, false, true,
             false, 0f, 0f, !float.IsNaN(limit), -limit, true);
    }

    void DrawSymmetry(List<JSONNode> reps, string[] repNos)
    {
        int n = reps.Count;
        var vals = new float[n];
        var cls = new string[n];
        float sum = 0f; int measured = 0;

        for (int i = 0; i < n; i++)
        {
            JSONNode r = reps[i];
            vals[i] = Num(r["sym_signed_deg"], out float sg) ? sg : float.NaN;
            if (Num(r["symmetry_deg"], out float d)) { sum += Mathf.Abs(d); measured++; }
            cls[i] = float.IsNaN(vals[i]) ? "dot-none" : "dot-plain";
        }

        Report(_symState, measured == 0 ? PostSetCopy.Unmeasured
                        : string.Format(PostSetCopy.SymHeading, sum / measured));
        Pill("sym", "neutral", PostSetCopy.PillReported);
        Big("sym", measured == 0 ? "-" : string.Format(PostSetCopy.DegBig, sum / measured));
        if (_symNum != null) _symNum.text = PostSetCopy.SymBigCap;

        Plot(_symPlot, _symY, _symX, vals, cls, repNos, null, false, true,
             false, 0f, 0f, false, 0f, true);
    }

    void DrawShoulders(List<JSONNode> reps, string[] repNos)
    {
        int n = reps.Count;
        var vals = new float[n];
        var cls = new string[n];
        float sum = 0f; int measured = 0;
        float even = float.NaN;

        for (int i = 0; i < n; i++)
        {
            JSONNode r = reps[i];
            vals[i] = Num(r["shoulder_tilt_deg"], out float t) ? -t : float.NaN;
            if (!float.IsNaN(vals[i])) { sum += Mathf.Abs(vals[i]); measured++; }
            string band = r["shoulder_band"].Value;
            cls[i] = float.IsNaN(vals[i]) || band == "unmeasured" ? "dot-none"
                   : band == "even" ? "dot-good" : "dot-warn";
            if (float.IsNaN(even) && Num(r["shoulder_even_deg"], out float e)) even = e;
        }

        Report(_shState, measured == 0 ? PostSetCopy.Unmeasured
                       : string.Format(PostSetCopy.ShHeading, sum / measured));
        Pill("sh", "neutral", PostSetCopy.PillReported);
        Big("sh", measured == 0 ? "-" : string.Format(PostSetCopy.DegBig, sum / measured));
        if (_shNum != null) _shNum.text = PostSetCopy.ShBigCap;

        bool hasBand = !float.IsNaN(even) && even > 0f;
        var extra = new List<float>();
        if (hasBand) { extra.Add(-even); extra.Add(even); }
        Plot(_shPlot, _shY, _shX, vals, cls, repNos, extra, false, true,
             hasBand, -even, even, false, 0f, true);
    }

    void DrawTiming(List<JSONNode> reps, string[] repNos)
    {
        int n = reps.Count;
        float down = 0f, up = 0f;
        int dn = 0, un = 0;

        _pauseTable?.Clear();
        AddRow(_pauseTable, PostSetCopy.RepCol, PostSetCopy.PauseCol, true, false);

        for (int i = 0; i < n; i++)
        {
            JSONNode r = reps[i];
            if (Num(r["descent_s"], out float d)) { down += d; dn++; }
            if (Num(r["ascent_s"], out float a)) { up += a; un++; }
            bool have = Num(r["bottom_dwell_s"], out float w);
            AddRow(_pauseTable, repNos[i], have ? w.ToString("0.0") : "-", false, i % 2 == 1);
        }

        float meanDown = dn > 0 ? down / dn : 0f;
        float meanUp = un > 0 ? up / un : 0f;
        if (_tempoState != null)
            _tempoState.text = string.Format(PostSetCopy.TempoState, meanDown, meanUp);
        Pill("tempo", "neutral", PostSetCopy.PillReported);
        if (_tempoDownVal != null) _tempoDownVal.text = string.Format(PostRepCopy.BarSeconds, meanDown);
        if (_tempoUpVal != null) _tempoUpVal.text = string.Format(PostRepCopy.BarSeconds, meanUp);
        Fill(_tempoDown, meanDown / tempoScaleS);
        Fill(_tempoUp, meanUp / tempoScaleS);
        BarAxis.Build(_tempoAxis, tempoScaleS);
    }

    static void AddRow(VisualElement table, string a, string b, bool header, bool alt)
    {
        if (table == null) return;
        var row = new VisualElement();
        row.AddToClassList("ptr");
        if (header) row.AddToClassList("ptr-head");
        else if (alt) row.AddToClassList("ptr-alt");
        var la = new Label(a); la.AddToClassList("ptd");
        var lb = new Label(b); lb.AddToClassList("ptd");
        if (header) { la.AddToClassList("ptd-h"); lb.AddToClassList("ptd-h"); }
        row.Add(la); row.Add(lb);
        table.Add(row);
    }

    void DrawRepNav(List<JSONNode> reps, string[] repNos)
    {
        if (_repNavNote != null)
            _repNavNote.text = reps.Count == 1 ? PostSetCopy.RepNavNoteOne
                             : string.Format(PostSetCopy.RepNavNote, reps.Count);
        int bad = 0;
        foreach (var r in reps) if (FaultCount(r) > 0) bad++;
        Pill("reps", bad > 0 ? "fault" : "good",
             bad > 0 ? string.Format(PostSetCopy.PillFlagged, bad) : PostSetCopy.PillAllClear);
        foreach (var nav in new[] { _repNav, _repNavTop })
        {
            if (nav == null) continue;
            nav.Clear();
            for (int i = 0; i < reps.Count; i++)
            {
                int index = i;
                var b = new Button(() => { if (flow != null) flow.ShowRepFromSet(index); })
                { text = repNos[i] };
                b.AddToClassList("repdot");
                if (FaultCount(reps[i]) > 0) b.AddToClassList("repdot-fault");
                nav.Add(b);
            }
        }
    }

    /// One measurement across the set: gridlines, an optional target band and threshold line, the series, and a dot per rep coloured by its verdict.
    void Plot(VisualElement plot, VisualElement yTicks, VisualElement xTicks,
              float[] vals, string[] cls, string[] repNos, List<float> extra,
              bool includeZero, bool symmetric,
              bool hasBand, float bandLo, float bandHi,
              bool hasLimit, float limit, bool zeroLine, bool openLo = false)
    {
        if (plot == null) return;
        plot.Clear(); yTicks?.Clear(); xTicks?.Clear();

        var all = new List<float>();
        foreach (float v in vals) if (!float.IsNaN(v)) all.Add(v);
        if (extra != null) all.AddRange(extra);
        Bounds(all, includeZero, symmetric, out float lo, out float hi, out int ticks);

        if (hasBand)
        {
            var band = new VisualElement();
            band.AddToClassList("chart-band");
            float top = YN(bandHi, lo, hi), bot = YN(openLo ? lo : bandLo, lo, hi);
            band.style.top = Length.Percent(top * 100f);
            band.style.height = Length.Percent(Mathf.Max(bot - top, 0f) * 100f);
            plot.Add(band);
        }

        var paint = new PaintElement();
        paint.style.position = Position.Absolute;
        paint.style.left = 0; paint.style.top = 0; paint.style.right = 0; paint.style.bottom = 0;
        plot.Add(paint);

        for (int i = 0; i < ticks; i++)
        {
            float y = ticks == 1 ? 0.5f : (float)i / (ticks - 1);
            paint.Add(new PaintElement.Path {
                points = new[] { new Vector2(0f, y), new Vector2(1f, y) },
                color = Grid, width = 1f });
        }
        if (zeroLine && lo < 0f && hi > 0f)
            paint.Add(new PaintElement.Path {
                points = new[] { new Vector2(0f, YN(0f, lo, hi)), new Vector2(1f, YN(0f, lo, hi)) },
                color = Zero, width = 1.5f });
        if (hasLimit)
            paint.Add(new PaintElement.Path {
                points = new[] { new Vector2(0f, YN(limit, lo, hi)), new Vector2(1f, YN(limit, lo, hi)) },
                color = Limit, width = 2f, dashed = true });

        int n = vals.Length;
        var run = new List<Vector2>();
        for (int i = 0; i < n; i++)
        {
            if (float.IsNaN(vals[i]))
            {
                if (run.Count > 1) AddRun(paint, run);
                run.Clear();
                continue;
            }
            run.Add(new Vector2((i + 0.5f) / n, YN(vals[i], lo, hi)));
        }
        if (run.Count > 1) AddRun(paint, run);

        for (int i = 0; i < n; i++)
        {
            if (float.IsNaN(vals[i])) continue;
            var dot = new VisualElement();
            dot.AddToClassList("dot");
            if (!string.IsNullOrEmpty(cls[i])) dot.AddToClassList(cls[i]);
            dot.style.left = Length.Percent((i + 0.5f) / n * 100f);
            dot.style.top = Length.Percent(YN(vals[i], lo, hi) * 100f);
            plot.Add(dot);
        }

        if (yTicks != null)
            for (int i = 0; i < ticks; i++)
            {
                float v = hi - (hi - lo) * (ticks == 1 ? 0f : (float)i / (ticks - 1));
                var l = new Label(v.ToString(Mathf.Abs(hi - lo) < 6f ? "0.0" : "0"));
                l.AddToClassList("y-tick");
                yTicks.Add(l);
            }

        if (xTicks != null)
            for (int i = 0; i < n; i++)
            {
                var l = new Label(repNos[i]);
                l.AddToClassList("x-tick");
                xTicks.Add(l);
            }
    }

    static void AddRun(PaintElement paint, List<Vector2> run)
    {
        paint.Add(new PaintElement.Path { points = run.ToArray(), color = Line, width = 2f });
    }

    /// Normalised y: 0 is the top of the plot, 1 the bottom.
    static float YN(float v, float lo, float hi)
    {
        if (hi - lo < 1e-6f) return 0.5f;
        return 1f - Mathf.Clamp01((v - lo) / (hi - lo));
    }

    /// Round axis limits out to a readable step, so the ticks are 0/100/200/300 rather than whatever the data happened to reach.
    static void Bounds(List<float> vals, bool includeZero, bool symmetric,
                       out float lo, out float hi, out int ticks)
    {
        lo = 0f; hi = 1f; ticks = 2;
        if (vals == null || vals.Count == 0) return;

        float min = float.MaxValue, max = float.MinValue;
        foreach (float v in vals) { if (v < min) min = v; if (v > max) max = v; }
        if (includeZero) { min = Mathf.Min(min, 0f); max = Mathf.Max(max, 0f); }
        if (symmetric) { float m = Mathf.Max(Mathf.Abs(min), Mathf.Abs(max)); min = -m; max = m; }

        float range = max - min;
        if (range < 1e-6f) { range = Mathf.Max(Mathf.Abs(max), 1f); max = min + range; }
        max += range * 0.12f;
        if (!includeZero) min -= range * 0.12f;
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

    static float NiceStep(float raw)
    {
        raw = Mathf.Max(raw, 1e-6f);
        float mag = Mathf.Pow(10f, Mathf.Floor(Mathf.Log10(raw)));
        float n = raw / mag;
        float s = n <= 1f ? 1f : n <= 2f ? 2f : n <= 5f ? 5f : 10f;
        return s * mag;
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

    /// Copied verbatim from PostRepUIController.DrawSymmetryIcon.
    void DrawSymIcon()
    {
        var p = AddPaint(_symIcon);
        if (p == null) return;
        var hipL = new Vector2(0.34f, 0.14f); var ankL = new Vector2(0.30f, 0.94f);
        var hipR = new Vector2(0.66f, 0.14f); var ankR = new Vector2(0.70f, 0.94f);
        var kneeL = new Vector2(0.24f, 0.46f);
        var kneeR = new Vector2(0.76f, 0.62f);
        Ln(p, IconBlue, 2.5f, false, hipL, hipR);
        Ln(p, IconBlue, 3f, false, hipL, kneeL, ankL);
        Ln(p, IconBlue, 3f, false, hipR, kneeR, ankR);
        Ln(p, IconGrey, 1.4f, true,
           new Vector2(0.10f, 0.46f), new Vector2(0.90f, 0.46f));
        Ln(p, IconGap, 2.5f, false,
           new Vector2(0.80f, 0.46f), new Vector2(0.80f, 0.62f));
    }

    /// Copied verbatim from PostRepUIController.DrawShoulderIcon - see above.
    void DrawShIcon()
    {
        var p = AddPaint(_shIcon);
        if (p == null) return;
        var shL = new Vector2(0.22f, 0.40f); var shR = new Vector2(0.78f, 0.62f);
        Ln(p, IconGrey, 1.4f, true,
           new Vector2(0.12f, 0.51f), new Vector2(0.88f, 0.51f));
        Ln(p, IconBlue, 2.5f, false, Ring(new Vector2(0.50f, 0.20f), 0.09f, 0.13f));
        Ln(p, IconBlue, 3.5f, false, shL, shR);
        Ln(p, IconBlue, 2.5f, false,
           new Vector2(0.50f, 0.51f), new Vector2(0.50f, 0.90f));
        Ln(p, IconGap, 2.5f, false, new Vector2(0.78f, 0.51f), shR);
    }

    static void Ln(PaintElement p, Color32 c, float w, bool dashed, params Vector2[] pts)
    {
        p?.Add(new PaintElement.Path { points = pts, color = c, width = w, dashed = dashed });
    }

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

    static string Cap(string s) =>
        string.IsNullOrEmpty(s) ? s : char.ToUpper(s[0]) + s.Substring(1);

    static void Fill(VisualElement bar, float f)
    {
        if (bar != null) bar.style.width = Length.Percent(Mathf.Clamp01(f) * 100f);
    }

    static void Set(Label l, string text, string cls)
    {
        if (l == null) return;
        l.text = text;
        l.EnableInClassList("state-warn", cls == "state-warn");
        l.EnableInClassList("state-neutral", false);
    }

    /// A bool the engine sent, or `fallback` if that report predates the field.
    static bool Flag(JSONNode n, bool fallback) =>
        (n == null || n.IsNull) ? fallback : n.AsBool;

    /// True if the engine put this fault id in the rep's `faults` list.
    static void Hide(VisualElement e)
    {
        if (e != null) e.style.display = DisplayStyle.None;
    }

    /// A line that STATES a measurement instead of judging it.
    static void Report(Label l, string text)
    {
        if (l == null) return;
        l.text = text;
        l.EnableInClassList("state-warn", false);
        l.EnableInClassList("state-neutral", true);
    }

    static bool Has(JSONNode r, string fault)
    {
        JSONNode f = r["faults"];
        if (f == null || f.IsNull) return false;
        for (int i = 0; i < f.Count; i++) if (f[i].Value == fault) return true;
        return false;
    }

    static int FaultCount(JSONNode r)
    {
        JSONNode f = r["faults"];
        return (f == null || f.IsNull) ? 0 : f.Count;
    }

    /// A usable number, or false.
    static bool Num(JSONNode n, out float v)
    {
        v = 0f;
        if (n == null || n.IsNull) return false;
        v = n.AsFloat;
        return !float.IsNaN(v) && !float.IsInfinity(v);
    }
}
