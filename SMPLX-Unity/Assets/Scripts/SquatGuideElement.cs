using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UIElements;

public class SquatGuideElement : VisualElement
{
    public const string CueBar   = "Pull the bar firmly against your upper back.";
    public const string CueFeet  = "Place your feet slightly wider than shoulder width.";
    public const string CueToes  = "Point your toes slightly outwards.";

    /// The depth sentence shown under the side view, per SessionSettings target.
    public static string DepthCue(string target)
    {
        switch (target)
        {
            case "partial": return "Bend your hips and knees, keeping your hips above knee height.";
            case "deep":    return "Lower until your hip crease is below the top of your knee.";
            default:        return "Lower until your hip crease is level with the top of your knee.";
        }
    }

    public enum View { Front, Side }

    struct Cmd { public Vector2[] pts; public Color col; public float w; public bool dashed; }

    static readonly Color Body   = new Color32(0x8f, 0x9c, 0xab, 255);
    static readonly Color Iron   = new Color32(0x3a, 0x3b, 0x3f, 255);
    static readonly Color Accent = new Color32(0x2a, 0x78, 0xd6, 255);
    static readonly Color Floor  = new Color32(0xc9, 0xc7, 0xc0, 255);

    readonly List<Cmd> _cmds = new List<Cmd>();
    readonly View _view;
    float _W, _H;

    public SquatGuideElement(View view, string target = "parallel")
    {
        _view = view;
        pickingMode = PickingMode.Ignore;
        generateVisualContent += Draw;
        SetTarget(target);
    }

    /// Rebuild the figure; only the side view depends on the target.
    public void SetTarget(string target)
    {
        _cmds.Clear();
        Clear();
        if (_view == View.Front) BuildFront(); else BuildSide(target);
        MarkDirtyRepaint();
    }

    void BuildFront()
    {
        _W = 460f; _H = 300f;
        Seg(Floor, 3f, false, V(120, 288), V(340, 288));
        Seg(Iron, 6f, false, V(140, 84), V(320, 84));
        Seg(Iron, 16f, false, V(152, 60), V(152, 108));
        Seg(Iron, 16f, false, V(308, 60), V(308, 108));
        Seg(Body, 34f, false, V(230, 96), V(230, 158));
        Seg(Body, 11f, false, V(208, 94), V(180, 128), V(176, 88));
        Seg(Body, 11f, false, V(252, 94), V(280, 128), V(284, 88));
        Seg(Body, 15f, false, V(220, 165), V(206, 218), V(198, 266));
        Seg(Body, 15f, false, V(240, 165), V(254, 218), V(262, 266));
        Seg(Body, 10f, false, V(198, 270), V(180, 281));
        Seg(Body, 10f, false, V(262, 270), V(280, 281));
        Disc(Body, V(230, 52), 17f);
        Arrow(V(176, 40), V(176, 72));
        Arrow(V(284, 40), V(284, 72));
        Seg(Accent, 2.5f, false, V(198, 296), V(262, 296));
        Seg(Accent, 2.5f, false, V(198, 291), V(198, 300));
        Seg(Accent, 2.5f, false, V(262, 291), V(262, 300));
        Seg(Accent, 1.5f, true, V(334, 48), V(292, 54));
        Seg(Accent, 1.5f, true, V(126, 252), V(196, 292));
        Arrow(V(334, 238), V(288, 277));

        Callout(CueBar, 336, 30, 124);
        Callout(CueFeet, 0, 222, 124);
        Callout(CueToes, 336, 222, 124);
    }

    void BuildSide(string target)
    {
        _W = 300f; _H = 300f;
        float knee = 81f, shin = 30f;
        if (target == "partial") { knee = 101f; shin = 22f; }
        else if (target == "deep") { knee = 37f; shin = 36f; }

        const float SHIN = 0.42f, THIGH = 0.43f, TRUNK = 0.50f, LIMB = 0.12f;
        Vector2 A = new Vector2(0f, 0.08f);
        float ps = shin * Mathf.Deg2Rad;
        Vector2 K = A + SHIN * new Vector2(Mathf.Sin(ps), Mathf.Cos(ps));
        float a = Mathf.Atan2(A.y - K.y, A.x - K.x);
        Vector2 h1 = K + THIGH * Dir(a + knee * Mathf.Deg2Rad);
        Vector2 h2 = K + THIGH * Dir(a - knee * Mathf.Deg2Rad);
        Vector2 H = h1.x < h2.x ? h1 : h2;
        float dx = Mathf.Clamp(0.05f - H.x, -0.45f, 0.45f);
        float lean = Mathf.Asin(dx / TRUNK);
        Vector2 up = new Vector2(Mathf.Sin(lean), Mathf.Cos(lean));
        Vector2 S = H + TRUNK * up;
        Vector2 back = new Vector2(-up.y, up.x);
        Vector2 bar = S + back * 0.07f + up * 0.03f;
        Vector2 head = S + up * 0.17f + new Vector2(0.03f, 0f);
        Vector2 elbow = S + back * 0.10f - up * 0.20f;

        float kTop = K.y + LIMB * 0.5f;
        Seg(Floor, 3f, false, M(-0.35f, 0f), M(0.45f, 0f));
        Seg(Accent, 2f, true, M(H.x - 0.18f, kTop), M(K.x + 0.14f, kTop));
        Ring(Floor, 2.5f, M(bar.x, bar.y), 0.225f * Scale);
        Seg(Body, 0.06f * Scale, false, M(-0.05f, 0.03f), M(0.19f, 0.03f));
        Seg(Body, LIMB * Scale, false, M(A), M(K), M(H));
        Seg(Body, 0.17f * Scale, false, M(H), M(S));
        Seg(Body, 0.07f * Scale, false, M(S), M(elbow), M(bar));
        Disc(Body, M(head), 0.10f * Scale);
        Disc(Iron, M(bar), 0.035f * Scale);
    }

    const float Scale = 200f;
    Vector2 M(Vector2 p) => M(p.x, p.y);
    Vector2 M(float x, float y) => new Vector2(140f + x * Scale, 285f - y * Scale);
    static Vector2 Dir(float a) => new Vector2(Mathf.Cos(a), Mathf.Sin(a));
    static Vector2 V(float x, float y) => new Vector2(x, y);

    void Seg(Color c, float w, bool dashed, params Vector2[] p) =>
        _cmds.Add(new Cmd { pts = p, col = c, w = w, dashed = dashed });

    void Disc(Color c, Vector2 at, float r) =>
        _cmds.Add(new Cmd { pts = new[] { at, at + new Vector2(0.01f, 0f) }, col = c, w = 2f * r });

    void Ring(Color c, float w, Vector2 at, float r)
    {
        var p = new Vector2[33];
        for (int i = 0; i <= 32; i++) p[i] = at + r * Dir(i * Mathf.PI / 16f);
        Seg(c, w, false, p);
    }

    void Arrow(Vector2 from, Vector2 to)
    {
        Seg(Accent, 2.5f, false, from, to);
        Vector2 d = (to - from).normalized, n = new Vector2(-d.y, d.x);
        Seg(Accent, 2.5f, false, to - d * 8f + n * 5f, to, to - d * 8f - n * 5f);
    }

    /// A text label placed in design units; positions are percentages so they track the drawing.
    void Callout(string text, float x, float y, float w)
    {
        var l = new Label(text);
        l.AddToClassList("guide-callout");
        l.style.position = Position.Absolute;
        l.style.left = Length.Percent(100f * x / _W);
        l.style.top = Length.Percent(100f * y / _H);
        l.style.width = Length.Percent(100f * w / _W);
        Add(l);
    }

    void Draw(MeshGenerationContext ctx)
    {
        Rect r = contentRect;
        if (r.width <= 1f || r.height <= 1f || _W <= 0f) return;
        float s = Mathf.Min(r.width / _W, r.height / _H);
        Vector2 o = new Vector2(r.x + (r.width - _W * s) * 0.5f, r.y + (r.height - _H * s) * 0.5f);
        var p = ctx.painter2D;
        p.lineJoin = LineJoin.Round;
        p.lineCap = LineCap.Round;
        foreach (var c in _cmds)
        {
            p.strokeColor = c.col;
            p.lineWidth = c.w * s;
            if (!c.dashed)
            {
                p.BeginPath();
                p.MoveTo(o + c.pts[0] * s);
                for (int i = 1; i < c.pts.Length; i++) p.LineTo(o + c.pts[i] * s);
                p.Stroke();
                continue;
            }
            for (int i = 1; i < c.pts.Length; i++)
            {
                Vector2 a = o + c.pts[i - 1] * s, b = o + c.pts[i] * s;
                float len = Vector2.Distance(a, b), dash = 6f * s, gap = 5f * s;
                if (len < 0.01f) continue;
                Vector2 dir = (b - a) / len;
                for (float d = 0f; d < len; d += dash + gap)
                {
                    p.BeginPath(); p.MoveTo(a + dir * d); p.LineTo(a + dir * Mathf.Min(d + dash, len)); p.Stroke();
                }
            }
        }
    }
}
