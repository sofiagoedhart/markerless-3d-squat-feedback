using UnityEngine;

[DefaultExecutionOrder(1000)]
public class CarriedBarbell : MonoBehaviour
{
    [Header("Wiring (left empty, found automatically)")]
    [Tooltip("Both avatar roots. The bar follows whichever one is active.")]
    public Transform[] avatarRoots;
    public ScreenFlowController flow;
    public BarHoldDetector barHold;

    [Header("Bar (metres, matching GymRoomBuilder)")]
    public float barLength = 2.20f;
    public float barRadius = 0.014f;
    public float sleeveLength = 0.40f;
    public float plateDiameter = 0.450f;
    public float plateThickness = 0.075f;
    [Range(0, 3)] public int platesPerSide = 2;

    [Header("Placement")]
    [Tooltip("How far behind the shoulder line the bar sits (high-bar: on the traps).")]
    public float behind = 0.075f;
    [Tooltip("How far above the shoulder-bone line the bar sits.")]
    public float above = 0.035f;
    [Tooltip("0 = on the traps (from the shoulders), 1 = through the centre of both fists.")]
    [Range(0f, 1f)] public float gripBlend = 1f;
    [Tooltip("Nudges the fist centre along the forearm, in metres (+ = towards the knuckles).")]
    public float fistOffset = 0.02f;
    [Tooltip("Shifts the gripped bar back from the fists, in metres, so it rests behind the neck.")]
    public float gripBack = 0.06f;
    [Tooltip("Drops the gripped bar below the fists, in metres, onto the traps.")]
    public float gripDown = 0.04f;
    [Tooltip("Closest the bar may come in front of the neck bone, in metres at avatar scale 1.")]
    public float neckClearance = 0.085f;

    Transform _bar, _root, _shoL, _shoR, _spine, _neck;
    Transform _eyeL, _eyeR, _head, _toeL, _toeR, _ankL, _ankR;
    Transform _wriL, _wriR, _knuL, _knuR;

    void Start()
    {
        if (flow == null) flow = FindAnyObjectByType<ScreenFlowController>();
        if (barHold == null) barHold = FindAnyObjectByType<BarHoldDetector>();
        if ((avatarRoots == null || avatarRoots.Length == 0))
        {
            var sw = FindAnyObjectByType<AvatarSwitcher>();
            if (sw != null) avatarRoots = new[] { sw.female, sw.male };
            else Debug.LogWarning("[CarriedBarbell] no avatarRoots and no AvatarSwitcher - bar disabled.");
        }
        _bar = Build().transform;
        _bar.gameObject.SetActive(false);
    }

    void OnDestroy() { if (_bar != null) Destroy(_bar.gameObject); }

    bool _carried;
    ScreenFlowController.Screen _lastScreen = ScreenFlowController.Screen.Setup;

    /// True when the bar should be on her back right now.
    bool Wanted()
    {
        if (flow == null) return true;
        var cur = flow.Current;
        if (cur == ScreenFlowController.Screen.Live && _lastScreen != ScreenFlowController.Screen.Live)
            _carried = barHold == null || barHold.Holding;
        _lastScreen = cur;
        if (cur == ScreenFlowController.Screen.Live) return _carried;
        return cur == ScreenFlowController.Screen.Setup
            && flow.Phase == ScreenFlowController.SetupPhase.Checking
            && barHold != null && barHold.Holding;
    }

    void LateUpdate()
    {
        if (_bar == null) return;
        Transform active = ActiveRoot();
        if (active != _root) Bind(active);

        bool want = Wanted() && _shoL != null && _shoR != null;
        if (_bar.gameObject.activeSelf != want) _bar.gameObject.SetActive(want);
        if (!want) return;

        Vector3 mid = (_shoL.position + _shoR.position) * 0.5f;
        Vector3 up = _spine != null ? (_spine.position - mid).normalized : Vector3.up;
        Vector3 front = Facing(up);
        Vector3 traps = mid - front * behind + up * above;
        Quaternion rot = Quaternion.LookRotation(front, up);
        if (gripBlend > 0f && FistCentre(_wriL, _knuL, out Vector3 fl) && FistCentre(_wriR, _knuR, out Vector3 fr))
        {
            Vector3 down = Vector3.Dot(up, Vector3.up) < 0f ? up : -up;
            Vector3 grip0 = (fl + fr) * 0.5f - front * gripBack + down * gripDown;
            _bar.position = Vector3.Lerp(traps, grip0, gripBlend);
            Vector3 axis = rot * Vector3.right, grip = fr - fl;
            if (grip.sqrMagnitude > 1e-6f)
            {
                if (Vector3.Dot(grip, axis) < 0f) grip = -grip;
                rot = Quaternion.Slerp(Quaternion.identity,
                                       Quaternion.FromToRotation(axis, grip.normalized), gripBlend) * rot;
            }
        }
        else _bar.position = traps;
        _bar.position = BehindNeck(_bar.position, front);
        _bar.rotation = rot;
    }

    /// Push the bar back if it has come forward of the neck; it is never pulled forward.
    Vector3 BehindNeck(Vector3 p, Vector3 front)
    {
        if (_neck == null || _root == null) return p;
        float clear = neckClearance * _root.lossyScale.y;
        float ahead = Vector3.Dot(p - _neck.position, front) + clear;
        return ahead > 0f ? p - front * ahead : p;
    }

    Transform ActiveRoot()
    {
        if (avatarRoots == null) return null;
        foreach (var r in avatarRoots) if (r != null && r.gameObject.activeInHierarchy) return r;
        return null;
    }

    /// Find the bones the bar is placed from, under the active avatar.
    void Bind(Transform root)
    {
        _root = root;
        _shoL = _shoR = _spine = _neck = _head = _eyeL = _eyeR = _toeL = _toeR = _ankL = _ankR = null;
        _wriL = _wriR = _knuL = _knuR = null;
        if (root == null) return;
        _shoL = Find(root, "left_shoulder");
        _shoR = Find(root, "right_shoulder");
        _spine = Find(root, "spine3") ?? Find(root, "neck");
        _head = Find(root, "head");
        _neck = Find(root, "neck");
        _eyeL = Find(root, "left_eye_smplhf");
        _eyeR = Find(root, "right_eye_smplhf");
        _toeL = Find(root, "left_foot");
        _toeR = Find(root, "right_foot");
        _ankL = Find(root, "left_ankle");
        _ankR = Find(root, "right_ankle");
        _wriL = Find(root, "left_wrist");
        _wriR = Find(root, "right_wrist");
        _knuL = Find(root, "left_middle1");
        _knuR = Find(root, "right_middle1");
        if (_shoL == null || _shoR == null)
            Debug.LogWarning("[CarriedBarbell] no shoulder bones under " + root.name);
        else Debug.Log("[CarriedBarbell] bar follows " + root.name);
    }

    /// Centre of a closed fist: just past the middle knuckle along the wrist-to-knuckle line.
    bool FistCentre(Transform wrist, Transform knuckle, out Vector3 c)
    {
        c = Vector3.zero;
        if (wrist == null) return false;
        if (knuckle == null) { c = wrist.position; return true; }
        Vector3 d = knuckle.position - wrist.position;
        c = knuckle.position + (d.sqrMagnitude > 1e-8f ? d.normalized * fistOffset : Vector3.zero);
        return true;
    }

    /// Which way the avatar looks, from the eyes (or toes), never from the mirrored shoulder line.
    Vector3 Facing(Vector3 up)
    {
        Vector3 f = Vector3.zero;
        if (_eyeL != null && _eyeR != null && _head != null)
            f = (_eyeL.position + _eyeR.position) * 0.5f - _head.position;
        if (f.sqrMagnitude < 1e-8f && _toeL != null && _toeR != null && _ankL != null && _ankR != null)
            f = (_toeL.position + _toeR.position - _ankL.position - _ankR.position) * 0.5f;
        if (f.sqrMagnitude < 1e-8f && _root != null) f = _root.forward;
        f = Vector3.ProjectOnPlane(f, up);
        if (f.sqrMagnitude < 1e-8f) f = Vector3.ProjectOnPlane(Vector3.forward, up);
        return f.normalized;
    }

    GameObject Build()
    {
        var chrome = Mat(new Color(0.780f, 0.790f, 0.800f), 0.90f, 0.85f);
        var rubber = Mat(new Color(0.120f, 0.120f, 0.130f), 0.00f, 0.25f);
        var bar = new GameObject("CarriedBarbell");
        Cyl(bar, "Shaft", Vector3.zero, new Vector3(barRadius * 2, barLength / 2, barRadius * 2), chrome);
        for (int s = -1; s <= 1; s += 2)
        {
            Cyl(bar, s < 0 ? "Sleeve-L" : "Sleeve-R",
                new Vector3(s * (barLength / 2 - sleeveLength / 2), 0, 0),
                new Vector3(0.05f, sleeveLength / 2, 0.05f), chrome);
            for (int i = 0; i < platesPerSide; i++)
                Cyl(bar, $"Plate-{(s < 0 ? "L" : "R")}{i}",
                    new Vector3(s * (barLength / 2 - sleeveLength + 0.06f + i * (plateThickness + 0.005f)), 0, 0),
                    new Vector3(plateDiameter, plateThickness / 2, plateDiameter), rubber);
        }
        return bar;
    }

    static Material Mat(Color c, float metallic, float smoothness)
    {
        var m = new Material(Shader.Find("Standard")) { color = c };
        if (m.HasProperty("_Metallic")) m.SetFloat("_Metallic", metallic);
        if (m.HasProperty("_Glossiness")) m.SetFloat("_Glossiness", smoothness);
        return m;
    }

    /// A cylinder lying along the bar's local X.
    static void Cyl(GameObject parent, string name, Vector3 pos, Vector3 scale, Material m)
    {
        var g = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
        g.name = name;
        g.transform.SetParent(parent.transform, false);
        g.transform.localPosition = pos;
        g.transform.localEulerAngles = new Vector3(0, 0, 90);
        g.transform.localScale = scale;
        var c = g.GetComponent<Collider>(); if (c != null) Destroy(c);
        g.GetComponent<Renderer>().sharedMaterial = m;
    }

    static Transform Find(Transform root, string name)
    {
        foreach (var t in root.GetComponentsInChildren<Transform>(true))
            if (t.name == name) return t;
        return null;
    }
}
