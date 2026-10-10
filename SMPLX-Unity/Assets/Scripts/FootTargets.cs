using UnityEngine;
using SimpleJSON;

public class FootTargets : MonoBehaviour
{
    [Header("Wiring")]
    public PoseUdpReceiver receiver;
    [Tooltip("Left empty, it is found in the scene. The targets are shown only " +
             "while the flow is in Setup/Checking.")]
    public ScreenFlowController flow;

    [Header("Placement")]
    [Tooltip("Floor height. Matches SMPLXPoseDriver.floorY.")]
    public float floorY = 0f;
    [Tooltip("Used until the stream reports the athlete's shoulder width.")]
    public float fallbackSeparationM = 0.36f;
    [Tooltip("Forward offset of the targets from the anchor, metres.")]
    public float forwardOffset = 0f;

    [Header("Look")]
    public float radius = 0.135f;
    [Tooltip("Dots in each dotted outline.")]
    [Range(8, 48)] public int dots = 22;
    public float dotSize = 0.022f;
    public Color idleColor = new Color(0.16f, 0.72f, 0.30f, 1f);
    public Color okColor = new Color(0.10f, 0.85f, 0.35f, 1f);
    [Range(0f, 1f)] public float fillAlpha = 0.28f;
    [Range(0f, 1f)] public float okFillAlpha = 0.45f;

    Transform _left, _right;
    Material _fillMat, _dotMat;
    float _sepM = -1f;
    bool _built, _ok;

    void OnEnable()
    {
        if (receiver == null) receiver = FindAnyObjectByType<PoseUdpReceiver>();
        if (flow == null) flow = FindAnyObjectByType<ScreenFlowController>();
        Build();
    }

    void Build()
    {
        if (_built) return;
        _fillMat = new Material(Shader.Find("Standard"));
        _fillMat.SetFloat("_Mode", 2f);
        _fillMat.SetInt("_SrcBlend", (int)UnityEngine.Rendering.BlendMode.SrcAlpha);
        _fillMat.SetInt("_DstBlend", (int)UnityEngine.Rendering.BlendMode.OneMinusSrcAlpha);
        _fillMat.SetInt("_ZWrite", 0);
        _fillMat.DisableKeyword("_ALPHATEST_ON");
        _fillMat.EnableKeyword("_ALPHABLEND_ON");
        _fillMat.DisableKeyword("_ALPHAPREMULTIPLY_ON");
        _fillMat.renderQueue = 3000;
        _fillMat.SetFloat("_Glossiness", 0f);

        _dotMat = new Material(Shader.Find("Standard"));
        _dotMat.SetFloat("_Glossiness", 0.1f);
        _dotMat.EnableKeyword("_EMISSION");

        _left  = MakeRing("FootTarget-L");
        _right = MakeRing("FootTarget-R");
        _built = true;
        Apply();
        Debug.Log($"[FootTargets] built at {transform.position}, separation "
                  + $"{Mathf.Max(_sepM, fallbackSeparationM) * 1000f:F0} mm. "
                  + "If these are not under the athlete, this object is not at the origin.");
    }

    Transform MakeRing(string name)
    {
        var g = new GameObject(name);
        g.hideFlags = HideFlags.DontSave;
        g.transform.SetParent(transform, false);

        var disc = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
        disc.name = "Fill";
        disc.transform.SetParent(g.transform, false);
        disc.transform.localPosition = new Vector3(0, 0.004f, 0);
        disc.transform.localScale = new Vector3(radius * 2f, 0.002f, radius * 2f);
        disc.GetComponent<Renderer>().sharedMaterial = _fillMat;
        DestroyImmediate(disc.GetComponent<Collider>());

        for (int i = 0; i < dots; i++)
        {
            float a = (i / (float)dots) * Mathf.PI * 2f;
            var d = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
            d.name = $"Dot{i}";
            d.transform.SetParent(g.transform, false);
            d.transform.localPosition =
                new Vector3(Mathf.Cos(a) * radius, 0.006f, Mathf.Sin(a) * radius);
            d.transform.localScale = new Vector3(dotSize, 0.003f, dotSize);
            d.GetComponent<Renderer>().sharedMaterial = _dotMat;
            DestroyImmediate(d.GetComponent<Collider>());
        }
        return g.transform;
    }

    void Update()
    {
        if (!_built) Build();

        bool show = flow == null ||
                    (flow.Current == ScreenFlowController.Screen.Setup &&
                     flow.Phase == ScreenFlowController.SetupPhase.Checking);
        if (_left  && _left.gameObject.activeSelf  != show) _left.gameObject.SetActive(show);
        if (_right && _right.gameObject.activeSelf != show) _right.gameObject.SetActive(show);
        if (!show) return;

        JSONNode pkt = receiver != null ? receiver.Latest : null;

        if (pkt != null)
        {
            JSONNode subj = pkt["subject"];
            JSONNode st = pkt["state"];
            JSONNode stance = (st != null && !st.IsNull) ? st["stance"] : null;

            if (subj != null && !subj.IsNull && !subj["shoulder_mm"].IsNull)
            {
                float shoulderM = subj["shoulder_mm"].AsFloat / 1000f;
                float lo = 1.0f, hi = 1.5f;
                if (stance != null && !stance.IsNull)
                {
                    if (!stance["lo"].IsNull) lo = stance["lo"].AsFloat;
                    if (!stance["hi"].IsNull) hi = stance["hi"].AsFloat;
                }
                float sep = shoulderM * (lo + hi) * 0.5f;
                if (sep > 0.05f && !Mathf.Approximately(sep, _sepM)) { _sepM = sep; Apply(); }
            }

            bool ok = stance != null && !stance.IsNull && stance["class"].Value == "medium";
            if (ok != _ok) { _ok = ok; Apply(); }
        }

        if (_sepM <= 0f) { _sepM = fallbackSeparationM; Apply(); }
    }

    void OnDrawGizmos()
    {
        float sep = _sepM > 0f ? _sepM : fallbackSeparationM;
        Gizmos.color = _ok ? okColor : idleColor;
        foreach (float sx in new[] { -sep * 0.5f, sep * 0.5f })
        {
            Vector3 c = transform.TransformPoint(new Vector3(sx, floorY, forwardOffset));
            const int N = 32;
            Vector3 prev = c + new Vector3(radius, 0, 0);
            for (int i = 1; i <= N; i++)
            {
                float a = (i / (float)N) * Mathf.PI * 2f;
                Vector3 pt = c + new Vector3(Mathf.Cos(a) * radius, 0, Mathf.Sin(a) * radius);
                Gizmos.DrawLine(prev, pt);
                prev = pt;
            }
        }
        Gizmos.DrawLine(transform.TransformPoint(new Vector3(-sep * 0.5f, floorY, forwardOffset)),
                        transform.TransformPoint(new Vector3( sep * 0.5f, floorY, forwardOffset)));
    }

    void Apply()
    {
        if (!_built) return;
        float half = Mathf.Max(_sepM, fallbackSeparationM) * 0.5f;
        if (_left)  _left.localPosition  = new Vector3(-half, floorY, forwardOffset);
        if (_right) _right.localPosition = new Vector3( half, floorY, forwardOffset);

        Color c = _ok ? okColor : idleColor;
        if (_fillMat != null)
            _fillMat.color = new Color(c.r, c.g, c.b, _ok ? okFillAlpha : fillAlpha);
        if (_dotMat != null)
        {
            _dotMat.color = c;
            _dotMat.SetColor("_EmissionColor", c * (_ok ? 1.1f : 0.55f));
        }
    }
}
