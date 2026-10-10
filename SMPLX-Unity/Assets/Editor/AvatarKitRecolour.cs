using System.IO;
using UnityEditor;
using UnityEngine;

public class AvatarKitRecolour : EditorWindow
{
    enum Sex { Female, Male }

    Sex _sex = Sex.Female;
    Color _top = new Color(0.11f, 0.11f, 0.13f);
    Color _bottom = new Color(0.055f, 0.055f, 0.067f);
    bool _doTop = true, _doBottom = true, _writeMask = false;
    Texture2D _result;
    string _variant = "";
    string _status = "";

    const string SrcFmt = "Assets/SMPLX/Textures/smplx_texture_{0}_alb.png";
    const string OutDir = "Assets/Avatars/Textures";
    const string OutFmt = OutDir + "/smplx_texture_{0}_alb_custom{1}.png";

    struct Window { public float h0, h1, s0, s1, v0, v1; public bool useHue; }

    static Window Spec(Sex sex, bool top)
    {
        if (sex == Sex.Female)
            return top
                ? new Window { useHue = false, s0 = 0.00f, s1 = 0.09f, v0 = 0.55f, v1 = 1.00f }
                : new Window { useHue = true, h0 = 180f, h1 = 235f, s0 = 0.12f, s1 = 0.55f, v0 = 0.08f, v1 = 0.58f };
        return top
            ? new Window { useHue = true, h0 = 6.5f, h1 = 10.0f, s0 = 0.18f, s1 = 0.34f, v0 = 0.60f, v1 = 0.80f }
            : new Window { useHue = true, h0 = 158f, h1 = 192f, s0 = 0.03f, s1 = 0.22f, v0 = 0.18f, v1 = 0.58f };
    }

    [MenuItem("Tools/Skripsie/Recolour Avatar Kit")]
    static void Open() => GetWindow<AvatarKitRecolour>("Avatar Kit");

    void OnGUI()
    {
        EditorGUILayout.LabelField("Recolour the avatar's clothing", EditorStyles.boldLabel);
        EditorGUILayout.HelpBox(
            "Edits the TEXTURE, not the material tint. Skin, face and hair are left alone.\n" +
            "Brightness is preserved, so folds and seams survive the recolour.",
            MessageType.None);
        EditorGUILayout.Space();

        _sex = (Sex)EditorGUILayout.EnumPopup("Avatar", _sex);
        _variant = EditorGUILayout.TextField(
            new GUIContent("Variant name",
                "Blank overwrites the character's current texture. A name - \"teal\", " +
                "\"black\" - writes a separate file you can add as a colourway in " +
                "AvatarSwitcher."),
            _variant);
        EditorGUILayout.Space();

        _doTop = EditorGUILayout.BeginToggleGroup("Recolour top", _doTop);
        _top = EditorGUILayout.ColorField("Top colour", _top);
        EditorGUILayout.EndToggleGroup();

        _doBottom = EditorGUILayout.BeginToggleGroup("Recolour bottom", _doBottom);
        _bottom = EditorGUILayout.ColorField("Bottom colour", _bottom);
        EditorGUILayout.EndToggleGroup();

        EditorGUILayout.Space();
        _writeMask = EditorGUILayout.Toggle(
            new GUIContent("Also write mask image",
                "Writes a magenta overlay next to the output so you can check what was selected."),
            _writeMask);

        EditorGUILayout.Space();
        using (new EditorGUI.DisabledScope(!_doTop && !_doBottom))
            if (GUILayout.Button("Apply to texture", GUILayout.Height(30)))
                Apply();

        if (GUILayout.Button("Reset to stock texture"))
        {
            _doTop = _doBottom = false; Apply(); _doTop = _doBottom = true;
        }

        if (!string.IsNullOrEmpty(_status))
        {
            EditorGUILayout.Space();
            EditorGUILayout.HelpBox(_status, MessageType.Info);
        }
        if (_result != null)
        {
            EditorGUILayout.Space();
            EditorGUILayout.LabelField("Result (UV layout)");
            var r = GUILayoutUtility.GetRect(position.width - 20, 240);
            EditorGUI.DrawPreviewTexture(r, _result, null, ScaleMode.ScaleToFit);
        }
    }

    static void RgbToHsv(float r, float g, float b, out float h, out float s, out float v)
    {
        float mx = Mathf.Max(r, Mathf.Max(g, b)), mn = Mathf.Min(r, Mathf.Min(g, b));
        v = mx;
        float d = mx - mn;
        s = mx <= 0f ? 0f : d / mx;
        if (d <= 0.0001f) { h = 0f; return; }
        if (mx == r) h = ((g - b) / d) % 6f;
        else if (mx == g) h = ((b - r) / d) + 2f;
        else h = ((r - g) / d) + 4f;
        h *= 60f; if (h < 0f) h += 360f;
    }

    void Apply()
    {
        string tag = _sex == Sex.Female ? "f" : "m";
        string src = string.Format(SrcFmt, tag);
        string suffix = string.IsNullOrWhiteSpace(_variant)
            ? "" : "_" + _variant.Trim().Replace(" ", "_").ToLowerInvariant();
        string outPath = string.Format(OutFmt, tag, suffix);

        if (!File.Exists(src)) { _status = "Cannot find " + src; return; }
        Directory.CreateDirectory(OutDir);

        var tex = new Texture2D(2, 2, TextureFormat.RGBA32, false);
        tex.LoadImage(File.ReadAllBytes(src));
        var px = tex.GetPixels32();
        int n = px.Length;
        var mask = _writeMask ? new Color32[n] : null;
        if (mask != null) System.Array.Copy(px, mask, n);

        int changed = 0;
        for (int pass = 0; pass < 2; pass++)
        {
            bool top = pass == 0;
            if (top && !_doTop) continue;
            if (!top && !_doBottom) continue;
            var w = Spec(_sex, top);
            Color tgt = top ? _top : _bottom;
            float tv = Mathf.Max(tgt.r, Mathf.Max(tgt.g, tgt.b));
            if (tv < 0.02f) { tgt = new Color(0.06f, 0.06f, 0.07f); tv = 0.07f; }

            double sum = 0; int cnt = 0;
            for (int i = 0; i < n; i++)
            {
                float r = px[i].r / 255f, g = px[i].g / 255f, b = px[i].b / 255f;
                RgbToHsv(r, g, b, out float h, out float s, out float v);
                if (s < w.s0 || s > w.s1 || v < w.v0 || v > w.v1) continue;
                if (w.useHue && (h < w.h0 || h > w.h1)) continue;
                sum += v; cnt++;
            }
            if (cnt == 0) { _status = (top ? "Top" : "Bottom") + ": nothing matched."; continue; }
            float refV = (float)(sum / cnt);

            EditorUtility.DisplayProgressBar("Recolouring", top ? "top" : "bottom", pass * 0.5f);
            for (int i = 0; i < n; i++)
            {
                float r = px[i].r / 255f, g = px[i].g / 255f, b = px[i].b / 255f;
                RgbToHsv(r, g, b, out float h, out float s, out float v);
                if (s < w.s0 || s > w.s1 || v < w.v0 || v > w.v1) continue;
                if (w.useHue && (h < w.h0 || h > w.h1)) continue;
                float scale = Mathf.Clamp(v / Mathf.Max(refV, 0.0001f), 0.35f, 1.9f);
                px[i] = new Color32(
                    (byte)(Mathf.Clamp01(tgt.r * scale) * 255f),
                    (byte)(Mathf.Clamp01(tgt.g * scale) * 255f),
                    (byte)(Mathf.Clamp01(tgt.b * scale) * 255f),
                    px[i].a);
                if (mask != null) mask[i] = new Color32(255, 0, 255, 255);
                changed++;
            }
        }
        EditorUtility.ClearProgressBar();

        tex.SetPixels32(px); tex.Apply(false);
        File.WriteAllBytes(outPath, tex.EncodeToPNG());

        if (mask != null)
        {
            var mt = new Texture2D(tex.width, tex.height, TextureFormat.RGBA32, false);
            mt.SetPixels32(mask); mt.Apply(false);
            File.WriteAllBytes(OutDir + "/../_mask_" + tag + ".png", mt.EncodeToPNG());
            DestroyImmediate(mt);
        }

        AssetDatabase.ImportAsset(outPath, ImportAssetOptions.ForceUpdate);
        var imp = AssetImporter.GetAtPath(outPath) as TextureImporter;
        if (imp != null && imp.maxTextureSize < 4096)
        {
            imp.maxTextureSize = 4096;
            imp.SaveAndReimport();
        }
        _result = AssetDatabase.LoadAssetAtPath<Texture2D>(outPath);
        _status = string.Format("{0:n0} pixels recoloured ({1:0.0}% of the texture).\nWrote {2}",
                                changed, 100f * changed / n, outPath);
        DestroyImmediate(tex);
        Repaint();
    }
}
