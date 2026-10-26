using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UIElements;
using SimpleJSON;

public class LiveDepthChart
{
    public float topMm = 470f;
    public float bottomMm = -80f;
    public float windowSeconds = 15f;
    public float tickSeconds = 5f;
    public float rightPad = 0.075f;
    public float narrowRepPx = 120f;
    public Color traceColor = new Color(0.165f, 0.471f, 0.839f);
    public Color standColor = new Color(0.043f, 0.043f, 0.043f, 0.28f);
    public Color gridColor = new Color(0.043f, 0.043f, 0.043f, 0.10f);

    const float GapSeconds = 0.6f;
    const float GuessRepSeconds = 3f;
    static readonly string[] Mods = { "on", "shallow", "past", "unmeasured", "current" };

    class Span
    {
        public int n;
        public float t0, t1 = float.NaN;
        public string mod = "current";
        public VisualElement slot, col, dot;
        public Label rep, chip;
    }

    VisualElement _panel, _plot, _slots, _labels, _dots, _band, _live, _done, _keyPast, _ticks;
    Label _target, _yStand, _yTarget;
    PaintElement _paint;

    readonly List<Vector2> _samples = new List<Vector2>();
    readonly List<Span> _spans = new List<Span>();
    readonly List<Label> _tickEls = new List<Label>();

    int _lastPacket = -1, _seenReps = 0;
    bool _armed = true, _frozen, _haveDm;
    float _tStart = float.NaN, _tFrozen = float.NaN, _standMm = float.NaN, _dm = float.NaN;
    Span _open;

    public VisualElement Panel => _panel;

    /// Looks the chart's elements up in a freshly built live-screen tree.
    public void Bind(VisualElement root)
    {
        _panel   = root.Q<VisualElement>("traj-panel");
        _plot    = root.Q<VisualElement>("traj-plot");
        _slots   = root.Q<VisualElement>("traj-slots");
        _labels  = root.Q<VisualElement>("traj-labels");
        _dots    = root.Q<VisualElement>("traj-dots");
        _band    = root.Q<VisualElement>("traj-band");
        _live    = root.Q<VisualElement>("traj-live");
        _done    = root.Q<VisualElement>("traj-complete");
        _keyPast = root.Q<VisualElement>("traj-key-past");
        _target  = root.Q<Label>("traj-target");
        _yStand  = root.Q<Label>("traj-y-stand");
        _yTarget = root.Q<Label>("traj-y-target");
        if (_panel == null || _plot == null)
            Debug.LogWarning("[LiveDepthChart] no traj-panel / traj-plot in the UXML; the trajectory will not show.");

        _paint = null;
        var host = root.Q<VisualElement>("traj-lines");
        if (host != null)
        {
            host.Clear();
            _paint = new PaintElement();
            _paint.style.position = Position.Absolute;
            _paint.style.left = 0; _paint.style.top = 0; _paint.style.right = 0; _paint.style.bottom = 0;
            host.Add(_paint);
        }
        _slots?.Clear(); _labels?.Clear(); _dots?.Clear();
        if (_labels != null) _labels.style.overflow = Overflow.Hidden;

        _tickEls.Clear();
        _ticks = null;
        if (_plot != null)
        {
            _ticks = new VisualElement();
            _ticks.AddToClassList("traj-layer");
            _ticks.pickingMode = PickingMode.Ignore;
            _plot.Add(_ticks);
        }
        foreach (var s in _spans) MakeEls(s);
        _lastPacket = -1;
    }

    /// Forgets the set in progress, for a new set or a fresh live screen.
    public void Reset()
    {
        foreach (var s in _spans) DropEls(s);
        _spans.Clear();
        _samples.Clear();
        _open = null;
        _armed = true;
        _frozen = false;
        _haveDm = false;
        _tStart = float.NaN;
        _tFrozen = float.NaN;
        _seenReps = 0;
        _lastPacket = -1;
    }

    /// Hides the live point while tracking is lost.
    public void HideLive() { Show(_live, false); }

    /// Reads the newest packet and redraws; call once per frame while the chart is shown.
    public void Tick(PoseUdpReceiver rx, JSONNode st, int target)
    {
        if (_panel == null || _plot == null || rx == null || st == null) return;
        target = Mathf.Max(1, target);

        int reps = rx.SetReps.Count;
        if (reps < _seenReps) Reset();

        if (rx.PacketCount != _lastPacket || _lastPacket < 0)
        {
            _lastPacket = rx.PacketCount;
            Ingest(rx, st, reps, target, Time.unscaledTime);
        }
        Redraw(st);
    }

    void Ingest(PoseUdpReceiver rx, JSONNode st, int reps, int target, float now)
    {
        if (float.IsNaN(_tStart)) _tStart = now;

        for (int i = _seenReps; i < reps; i++)
        {
            Span s = _open;
            if (s == null)
            {
                float prev = _spans.Count > 0 ? _spans[_spans.Count - 1].t1 : _tStart;
                s = NewSpan(Mathf.Max(prev, now - GuessRepSeconds));
            }
            s.t1 = now;
            s.n = i + 1;
            s.mod = Verdict(rx.SetReps[i]);
            _open = null;
            _armed = false;
        }
        _seenReps = reps;

        _haveDm = st["depth_mm"] != null && !st["depth_mm"].IsNull;
        _dm = _haveDm ? st["depth_mm"].AsFloat : float.NaN;

        if (st["phase"].Value == "SETUP")
        {
            _armed = true;
            if (_haveDm) _standMm = float.IsNaN(_standMm) ? _dm : Mathf.Lerp(_standMm, _dm, 0.1f);
        }
        else if (_armed && _open == null && !_frozen)
        {
            _open = NewSpan(now);
            _open.n = reps + 1;
            _armed = false;
        }

        if (_haveDm && !_frozen) _samples.Add(new Vector2(now, _dm));
        if (!_frozen && reps >= target) { _frozen = true; _tFrozen = now; }

        float keep = now - windowSeconds - 2f;
        int drop = 0;
        while (drop < _samples.Count - 1 && _samples[drop + 1].x < keep) drop++;
        if (drop > 0) _samples.RemoveRange(0, drop);
        for (int i = _spans.Count - 1; i >= 0; i--)
            if (!float.IsNaN(_spans[i].t1) && _spans[i].t1 < keep) { DropEls(_spans[i]); _spans.RemoveAt(i); }
    }

    void Redraw(JSONNode st)
    {
        JSONNode tgt = st["depth_target"];
        bool haveTgt = tgt != null && !tgt.IsNull && tgt["hi"] != null && !tgt["hi"].IsNull;
        bool openLo = haveTgt && (tgt["lo"] == null || tgt["lo"].IsNull);
        float hi = haveTgt ? tgt["hi"].AsFloat : float.NaN;
        float lo = haveTgt && !openLo ? tgt["lo"].AsFloat : float.NegativeInfinity;
        string name = haveTgt ? tgt["name"].Value : "";

        if (_target != null) _target.text = name.ToUpper();
        Show(_band, haveTgt); Show(_yTarget, haveTgt);
        Show(_keyPast, name != "deep");
        if (haveTgt)
        {
            float a = Y(hi), b = openLo ? 1f : Y(lo);
            _band.style.top = Length.Percent(a * 100f);
            _band.style.height = Length.Percent(Mathf.Max(b - a, 0f) * 100f);
            _band.EnableInClassList("open-below", openLo);
            if (_yTarget != null) _yTarget.style.top = Length.Percent((a + b) * 50f);
        }

        _paint?.Clear();
        bool standKnown = !float.IsNaN(_standMm);
        float ys = standKnown ? Y(_standMm) : 0f;
        if (_yStand != null) _yStand.style.top = Length.Percent(ys * 100f);
        if (standKnown)
            _paint?.Add(new PaintElement.Path {
                points = new[] { new Vector2(0f, ys), new Vector2(1f, ys) },
                color = standColor, width = 2f, dashed = true });

        if (float.IsNaN(_tStart)) { Show(_live, false); Show(_done, false); return; }

        float lastT = _samples.Count > 0 ? _samples[_samples.Count - 1].x : _tStart;
        float tNow = _frozen ? _tFrozen : Mathf.Min(Time.unscaledTime, lastT + 0.15f);
        float span = SpanSeconds();
        float tRight = Mathf.Max(_tStart + span, tNow + rightPad * span);
        float tLeft = tRight - span;

        DrawTicks(tLeft, tRight);

        var seg = new List<Vector2>();
        float prevT = float.NaN;
        foreach (var s in _samples)
        {
            if (!float.IsNaN(prevT) && s.x - prevT > GapSeconds) { Flush(seg); seg = new List<Vector2>(); }
            seg.Add(new Vector2(X(s.x, tLeft), Y(s.y)));
            prevT = s.x;
        }
        Flush(seg);

        float plotW = _plot.contentRect.width;
        foreach (var s in _spans) PlaceSpan(s, tLeft, tNow, plotW);

        Show(_done, _frozen);
        bool showLive = !_frozen && _haveDm && _samples.Count > 0;
        Show(_live, showLive);
        if (showLive)
        {
            _live.style.left = Length.Percent(X(lastT, tLeft) * 100f);
            _live.style.top = Length.Percent(Y(_dm) * 100f);
            _live.EnableInClassList("in-band", haveTgt && _dm >= lo && _dm <= hi);
        }
    }

    void DrawTicks(float tLeft, float tRight)
    {
        int used = 0;
        if (_ticks != null && tickSeconds > 0f)
        {
            int k0 = Mathf.Max(1, Mathf.CeilToInt((tLeft - _tStart) / tickSeconds));
            for (int k = k0; _tStart + k * tickSeconds <= tRight; k++)
            {
                float x = X(_tStart + k * tickSeconds, tLeft);
                _paint?.Add(new PaintElement.Path {
                    points = new[] { new Vector2(x, 0f), new Vector2(x, 1f) },
                    color = gridColor, width = 1f });
                if (used == _tickEls.Count)
                {
                    var l = new Label();
                    l.AddToClassList("traj-tick");
                    l.pickingMode = PickingMode.Ignore;
                    _ticks.Add(l);
                    _tickEls.Add(l);
                }
                var lab = _tickEls[used++];
                lab.text = $"{k * tickSeconds:0} s";
                lab.style.left = Length.Percent(x * 100f);
                Show(lab, true);
            }
        }
        for (int i = used; i < _tickEls.Count; i++) Show(_tickEls[i], false);
    }

    void PlaceSpan(Span s, float tLeft, float tNow, float plotW)
    {
        bool open = float.IsNaN(s.t1);
        float x0 = X(s.t0, tLeft), x1 = X(open ? tNow : s.t1, tLeft);
        bool visible = x1 > 0f && x1 > x0;
        Show(s.slot, visible); Show(s.col, visible);
        if (!visible) { Show(s.dot, false); return; }

        Place(s.slot, x0, x1);
        Place(s.col, Mathf.Max(x0, 0f), x1);
        SetMod(s.slot, "traj-slot--", s.mod);

        bool narrow = plotW > 1f && (x1 - x0) * plotW < narrowRepPx;
        s.rep.text = narrow ? s.n.ToString() : "Rep " + s.n;
        s.rep.EnableInClassList("traj-rep--live", true);

        if (open)
        {
            Show(s.chip, false);
            Show(s.dot, false);
            return;
        }
        s.chip.text = narrow ? "" : ChipText(s.mod);
        SetMod(s.chip, "traj-chip--", s.mod);
        s.chip.EnableInClassList("traj-chip--dot", narrow);
        Show(s.chip, true);

        bool found = false;
        Vector2 low = Vector2.zero;
        foreach (var p in _samples)
            if (p.x >= s.t0 && p.x <= s.t1 && (!found || p.y < low.y)) { low = p; found = true; }
        Show(s.dot, found);
        if (found)
        {
            SetMod(s.dot, "traj-dot--", s.mod);
            s.dot.style.left = Length.Percent(X(low.x, tLeft) * 100f);
            s.dot.style.top = Length.Percent(Y(low.y) * 100f);
        }
    }

    Span NewSpan(float t0)
    {
        var s = new Span { t0 = t0 };
        MakeEls(s);
        _spans.Add(s);
        return s;
    }

    void MakeEls(Span s)
    {
        s.slot = new VisualElement();
        s.slot.AddToClassList("traj-slot");
        s.slot.pickingMode = PickingMode.Ignore;
        _slots?.Add(s.slot);

        s.col = new VisualElement();
        s.col.AddToClassList("traj-col");
        s.rep = new Label();
        s.rep.AddToClassList("traj-rep");
        s.chip = new Label();
        s.chip.AddToClassList("traj-chip");
        s.col.Add(s.rep); s.col.Add(s.chip);
        _labels?.Add(s.col);

        s.dot = new VisualElement();
        s.dot.AddToClassList("traj-dot");
        s.dot.pickingMode = PickingMode.Ignore;
        _dots?.Add(s.dot);
    }

    static void DropEls(Span s)
    {
        s.slot?.RemoveFromHierarchy();
        s.col?.RemoveFromHierarchy();
        s.dot?.RemoveFromHierarchy();
    }

    void Flush(List<Vector2> seg)
    {
        if (seg.Count >= 2)
            _paint?.Add(new PaintElement.Path { points = seg.ToArray(), color = traceColor, width = 4f });
    }

    static void Place(VisualElement e, float x0, float x1)
    {
        e.style.left = Length.Percent(x0 * 100f);
        e.style.width = Length.Percent((x1 - x0) * 100f);
    }

    float SpanSeconds() => Mathf.Max(windowSeconds, 1f) / (1f - Mathf.Clamp(rightPad, 0f, 0.5f));

    float X(float t, float tLeft) => (t - tLeft) / SpanSeconds();

    float Y(float mm) => Mathf.Clamp01((topMm - mm) / Mathf.Max(topMm - bottomMm, 1f));

    /// The engine's depth verdict for a finished rep, as read by the review screens.
    static string Verdict(JSONNode r)
    {
        JSONNode f = r["faults"];
        if (f != null)
            for (int i = 0; i < f.Count; i++)
                if (f[i].Value == "depth_unmeasured") return "unmeasured";
        string met = r["depth_met"].Value;
        if (met == "True" || met == "true") return "on";
        if (met == "deeper") return "past";
        return "shallow";
    }

    static string ChipText(string mod)
    {
        switch (mod)
        {
            case "on": return PostRepCopy.PillOnTarget;
            case "past": return PostRepCopy.PillDeeper;
            case "unmeasured": return PostRepCopy.PillUnmeasured;
            default: return PostRepCopy.PillShallow;
        }
    }

    static void SetMod(VisualElement e, string prefix, string mod)
    {
        if (e == null) return;
        foreach (var m in Mods) e.EnableInClassList(prefix + m, m == mod);
    }

    static void Show(VisualElement e, bool on)
    {
        if (e != null) e.EnableInClassList("hidden", !on);
    }
}
