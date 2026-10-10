using UnityEngine;
using UnityEngine.UIElements;

/// The seconds axis under the timing bars: one tick per whole second up to the bar's full scale, so a bar can be read without its value label.
public static class BarAxis
{
    public static void Build(VisualElement axis, float scaleS)
    {
        if (axis == null || scaleS <= 0f) return;
        axis.Clear();
        int last = Mathf.FloorToInt(scaleS + 1e-3f);
        for (int s = 0; s <= last; s++)
        {
            var t = new Label(s.ToString());
            t.AddToClassList("tick");
            t.style.left = Length.Percent(100f * s / scaleS);
            axis.Add(t);
        }
        var unit = new Label(PostRepCopy.AxisSeconds);
        unit.AddToClassList("tick-unit");
        axis.Add(unit);
    }
}
