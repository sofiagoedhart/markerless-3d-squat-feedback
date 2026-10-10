using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UIElements;

public class PaintElement : VisualElement
{
    public class Path
    {
        public Vector2[] points;
        public Color color = Color.black;
        public float width = 2f;
        /// Dashed lines are for reference geometry (a level line, a straight hip-to-ankle line) so measured data and drawn-in references never look like the same kind of thing.
        public bool dashed = false;
        public float dashPx = 6f, gapPx = 5f;
        /// Set to shade the area between the line and `fillTo`, for a trace whose distance from a baseline is the reading.
        public Color? fillColor = null;
        public float fillTo = 1f;
    }

    readonly List<Path> _paths = new List<Path>();

    public PaintElement()
    {
        generateVisualContent += Draw;
        pickingMode = PickingMode.Ignore;
        style.flexGrow = 1;
    }

    public PaintElement Add(Path p) { _paths.Add(p); MarkDirtyRepaint(); return this; }
    public new void Clear() { _paths.Clear(); MarkDirtyRepaint(); }

    void Draw(MeshGenerationContext ctx)
    {
        Rect r = contentRect;
        if (r.width <= 1f || r.height <= 1f) return;
        var p = ctx.painter2D;

        foreach (var path in _paths)
        {
            if (path.points == null || path.points.Length < 2) continue;
            if (path.fillColor.HasValue)
            {
                p.fillColor = path.fillColor.Value;
                p.BeginPath();
                p.MoveTo(To(new Vector2(path.points[0].x, path.fillTo), r));
                foreach (var q in path.points) p.LineTo(To(q, r));
                p.LineTo(To(new Vector2(path.points[path.points.Length - 1].x, path.fillTo), r));
                p.ClosePath();
                p.Fill();
            }
            p.lineWidth = path.width;
            p.strokeColor = path.color;
            p.lineJoin = LineJoin.Round;
            p.lineCap = LineCap.Round;

            if (!path.dashed)
            {
                p.BeginPath();
                p.MoveTo(To(path.points[0], r));
                for (int i = 1; i < path.points.Length; i++) p.LineTo(To(path.points[i], r));
                p.Stroke();
                continue;
            }

            for (int i = 1; i < path.points.Length; i++)
            {
                Vector2 a = To(path.points[i - 1], r), b = To(path.points[i], r);
                float len = Vector2.Distance(a, b);
                if (len < 0.01f) continue;
                Vector2 dir = (b - a) / len;
                float step = path.dashPx + path.gapPx;
                for (float d = 0f; d < len; d += step)
                {
                    Vector2 s = a + dir * d;
                    Vector2 e = a + dir * Mathf.Min(d + path.dashPx, len);
                    p.BeginPath(); p.MoveTo(s); p.LineTo(e); p.Stroke();
                }
            }
        }
    }

    static Vector2 To(Vector2 n, Rect r) => new Vector2(r.x + n.x * r.width, r.y + n.y * r.height);
}
