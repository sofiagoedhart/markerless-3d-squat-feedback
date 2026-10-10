using System.Collections.Generic;
using UnityEngine;

public class AvatarSwitcher : MonoBehaviour
{
    [System.Serializable]
    public class Colourway
    {
        [Tooltip("Shown on the Settings button, so name it the way the athlete " +
                 "would: \"Purple\", \"Black\", \"Teal\".")]
        public string name = "Default";
        [Tooltip("Albedo to swap in. Leave empty to keep the prefab's own texture " +
                 "and only apply the tint below.")]
        public Texture2D albedo;
        [Tooltip("Colour multiplied over the albedo; keep near white, since it tints the skin too.")]
        public Color tint = Color.white;
    }

    [Header("Camera")]
    [Tooltip("Re-solve the camera framing when the character changes.")]
    public bool reframeOnSwitch = false;

    [Header("Wiring")]
    public SMPLXPoseDriver driver;
    public AvatarFramer framer;
    [Tooltip("Root of each character — the object holding the SMPLX component.")]
    public Transform female;
    public Transform male;

    [Header("Per-character display constants")]
    [Tooltip("Ankle joint to sole in metres for each character (display only).")]
    public float femaleFootDropM = 0.07f;
    public float maleFootDropM = 0.07f;

    [Header("Clothing")]
    public Colourway[] femaleColourways = new Colourway[0];
    public Colourway[] maleColourways = new Colourway[0];

    SessionSettings.Avatar _shown = (SessionSettings.Avatar)0;
    int _shownCloth = -1;

    void OnEnable()
    {
        SessionSettings.Changed += Apply;
        Apply();
    }

    void OnDisable() { SessionSettings.Changed -= Apply; }

    /// The names the Settings screen puts on the clothing button.
    public string[] ColourwayNames(SessionSettings.Avatar who)
    {
        var set = who == SessionSettings.Avatar.Male ? maleColourways : femaleColourways;
        var names = new List<string>();
        foreach (var c in set) names.Add(string.IsNullOrEmpty(c.name) ? "Default" : c.name);
        return names.ToArray();
    }

    public void Apply()
    {
        if (driver == null) driver = FindAnyObjectByType<SMPLXPoseDriver>();
        if (driver == null || female == null || male == null) return;

        var want = SessionSettings.AvatarChoice;
        Transform root = want == SessionSettings.Avatar.Male ? male : female;
        Transform other = want == SessionSettings.Avatar.Male ? female : male;

        if (want != _shown)
        {
            root.gameObject.SetActive(true);
            driver.SwitchAvatar(root);
            other.gameObject.SetActive(false);
            if (framer == null) framer = FindAnyObjectByType<AvatarFramer>();
            if (framer != null)
            {
                framer.target = root;
                if (reframeOnSwitch) framer.Reframe();
            }
            driver.footDropM = want == SessionSettings.Avatar.Male
                             ? maleFootDropM : femaleFootDropM;
            _shown = want;
            _shownCloth = -1;
            Debug.Log($"[AvatarSwitcher] showing {want}");
        }

        ApplyClothing(want, root);
    }

    void ApplyClothing(SessionSettings.Avatar who, Transform root)
    {
        var set = who == SessionSettings.Avatar.Male ? maleColourways : femaleColourways;
        if (set == null || set.Length == 0) return;
        int i = Mathf.Clamp(SessionSettings.ClothingIndex, 0, set.Length - 1);
        if (i == _shownCloth) return;
        _shownCloth = i;

        var c = set[i];
        foreach (var r in root.GetComponentsInChildren<Renderer>(true))
        {
            var m = r.material;
            if (c.albedo != null)
            {
                if (m.HasProperty("_BaseMap")) m.SetTexture("_BaseMap", c.albedo);
                if (m.HasProperty("_MainTex")) m.SetTexture("_MainTex", c.albedo);
            }
            if (m.HasProperty("_BaseColor")) m.SetColor("_BaseColor", c.tint);
            if (m.HasProperty("_Color")) m.SetColor("_Color", c.tint);
        }
    }
}
