using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UIElements;
using SimpleJSON;

public class LiveDepthChart
{
    public float topMm = 470f;
    public float bottomMm = -80f;
    public int slotSamples = 32;
    public float narrowSlotPx = 120f;
    public Color traceColor = new Color(0.165f, 0.471f, 0.839f);
    public Color standColor = new Color(0.043f, 0.043f, 0.043f, 0.28f);

    const int LeadMax = 10;
    static readonly string[] Mods = { "on", "shallow", "past", "unmeasured", "current" };

    VisualElement _panel, _plot, _slots, _labels, _dots, _band, _live, _done, _keyPast;
    Label _target, _yStand, _yTarget;
    PaintElement _paint;

    readonly List<VisualElement> _slotEls = new List<VisualElement>();
    readonly List<VisualElement> _dotEls = new List<VisualElement>();
    readonly List<Label> _repEls = new List<Label>();
    readonly List<Label> _chipEls = new List<Label>();
    readonly List<float> _current = new List<float>();
    readonly List<float> _lead = new List<float>();
    readonly Dictionary<int, List<float>> _leadIns = new Dictionary<int, List<float>>();

    int _slotCount = -1, _lastPacket = -1, _seenReps = 0;
    bool _inRep, _armed = true;
    float _standMm = float.NaN;

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
        _slotCount = -1;
        _lastPacket = -1;
    }

    /// Forgets the set in progress, for a new set or a fresh live screen.
    public void Reset()
    {
        _current.Clear();
        _lead.Clear();
        _leadIns.Clear();
        _inRep = false;
        _armed = true;
        _seenReps = 0;
        _lastPacket = -1;
    }

    /// Hides the live point while tracking is lost.
    public void HideLive() { Show(_live, false); }

    /// Reads the newest packet and redraws; call once per frame while the chart is shown.
    public void Tick(PoseUdpReceiver rx, JSONNode st, int target)
    {
        if (_panel == null || _plot == null || rx == null || st == null) return;
        BuildSlots(Mathf.Max(1, target));

        int reps = rx.SetReps.Count;
        if (reps < _seenReps) Reset();
        if (reps > _seenReps) { _current.Clear(); _lead.Clear(); _inRep = false; _armed = false; }
        _seenReps = reps;

        if (rx.PacketCount == _lastPacket && _lastPacket >= 0) return;
        _lastPacket = rx.PacketCount;

        bool haveDm = st["depth_mm"] != null && !st["depth_mm"].IsNull;
        float dm = haveDm ? st["depth_mm"].AsFloat : float.NaN;
        bool setup = st["phase"].Value == "SETUP";
        if (setup)
        {
            if (_inRep) { _lead.AddRange(_current); _current.Clear(); _inRep = false; }
            _armed = true;
            if (haveDm) _standMm = float.IsNaN(_standMm) ? dm : Mathf.Lerp(_standMm, dm, 0.1f);
        }
        else if (_armed && !_inRep)
        {
            _leadIns[reps] = new List<float>(_lead);
            _current.Clear();
            _inRep = true;
            _armed = false;
        }
        if (haveDm)
        {
            if (_inRep) _current.Add(dm);
            else _lead.Add(dm);
        }
        if (_lead.Count > LeadMax) _lead.RemoveRange(0, _lead.Count - LeadMax);
        Redraw(rx, st, haveDm, dm);
    }

    void BuildSlots(int n)
    {
        if (n == _slotCount && _slotEls.Count == n) return;
        _slotCount = n;
        _slots?.Clear(); _labels?.Clear(); _dots?.Clear();
        _slotEls.Clear(); _repEls.Clear(); _chipEls.Clear(); _dotEls.Clear();
        for (int i = 0; i < n; i++)
        {
            var slot = new VisualElement();
            slot.AddToClassList("traj-slot");
            slot.style.left = Length.Percent(100f * i / n);
            slot.style.width = Length.Percent(100f / n);
            slot.pickingMode = PickingMode.Ignore;
            _slots?.Add(slot);
            _slotEls.Add(slot);

            var col = new VisualElement();
            col.AddToClassList("traj-col");
            col.style.left = Length.Percent(100f * i / n);
            col.style.width = Length.Percent(100f / n);
            var rep = new Label();
            rep.AddToClassList("traj-rep");
            var chip = new Label();
            chip.AddToClassList("traj-chip");
            col.Add(rep); col.Add(chip);
            _labels?.Add(col);
            _repEls.Add(rep); _chipEls.Add(chip);

            var dot = new VisualElement();
            dot.AddToClassList("traj-dot");
            dot.pickingMode = PickingMode.Ignore;
            _dots?.Add(dot);
            _dotEls.Add(dot);
        }
    }

    void Redraw(PoseUdpReceiver rx, JSONNode st, bool haveDm, float dm)
    {
        int n = _slotCount;
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

        float plotW = _plot.contentRect.width;
        bool narrow = plotW > 1f && plotW / n < narrowSlotPx;
        int done = Mathf.Min(rx.SetReps.Count, n);
        Vector2 liveAt = new Vector2((float)done / n, haveDm ? Y(dm) : ys);
        var line = new List<Vector2>();

        for (int i = 0; i < n; i++)
        {
            string mod = null;
            var rep = _repEls[i];
            var chip = _chipEls[i];
            var dot = _dotEls[i];
            rep.text = narrow ? (i + 1).ToString() : "Rep " + (i + 1);

            if (i < done)
            {
                JSONNode r = rx.SetReps[i];
                mod = Verdict(r);
                List<float> vals = LeadIn(i);
                vals.AddRange(Values(r["trace"]));
                if (vals.Count >= 2)
                {
                    Vector2[] pts = SlotPath(i, n, vals, true);
                    line.AddRange(pts);
                    Vector2 low = pts[0];
                    foreach (var p in pts) if (p.y > low.y) low = p;
                    dot.style.left = Length.Percent(low.x * 100f);
                    dot.style.top = Length.Percent(low.y * 100f);
                    Show(dot, true);
                }
                else Show(dot, false);
                chip.text = narrow ? "" : ChipText(mod);
                SetMod(chip, "traj-chip--", mod);
                SetMod(dot, "traj-dot--", mod);
                chip.EnableInClassList("traj-chip--dot", narrow);
                Show(chip, true);
            }
            else
            {
                Show(dot, false);
                Show(chip, false);
                if (i == done)
                {
                    mod = "current";
                    List<float> vals = _inRep ? LeadIn(i) : new List<float>(_lead);
                    if (_inRep) vals.AddRange(_current);
                    if (vals.Count >= 1)
                    {
                        Vector2[] pts = SlotPath(i, n, vals, false);
                        line.AddRange(pts);
                        liveAt = pts[pts.Length - 1];
                    }
                }
            }
            rep.EnableInClassList("traj-rep--live", i <= done);
            SetMod(_slotEls[i], "traj-slot--", mod);
        }

        bool complete = done >= n;
        Show(_done, complete);
        bool showLive = !complete && haveDm;
        if (line.Count >= 2)
            _paint?.Add(new PaintElement.Path { points = line.ToArray(), color = traceColor, width = 4f });
        Show(_live, showLive);
        if (showLive)
        {
            _live.style.left = Length.Percent(liveAt.x * 100f);
            _live.style.top = Length.Percent(liveAt.y * 100f);
            _live.EnableInClassList("in-band", haveTgt && dm >= lo && dm <= hi);
        }
    }

    /// Maps a slot's samples across it; a finished slot fills it exactly, a live one grows into it.
    Vector2[] SlotPath(int slot, int n, List<float> vals, bool final)
    {
        int c = vals.Count;
        float denom = final ? Mathf.Max(c - 1, 1) : Mathf.Max(slotSamples + LeadMax, c - 1);
        var pts = new Vector2[c];
        for (int k = 0; k < c; k++)
            pts[k] = new Vector2((slot + Mathf.Min(k / denom, 1f)) / n, Y(vals[k]));
        return pts;
    }

    List<float> LeadIn(int slot)
    {
        List<float> v;
        return _leadIns.TryGetValue(slot, out v) ? new List<float>(v) : new List<float>();
    }

    float Y(float mm) => Mathf.Clamp01((topMm - mm) / Mathf.Max(topMm - bottomMm, 1f));

    static List<float> Values(JSONNode trace)
    {
        var v = new List<float>();
        if (trace == null || trace.IsNull) return v;
        for (int i = 0; i < trace.Count; i++)
            if (!trace[i].IsNull) v.Add(trace[i].AsFloat);
        return v;
    }

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
