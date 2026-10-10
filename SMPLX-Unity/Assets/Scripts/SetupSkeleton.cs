using UnityEngine;
using SimpleJSON;

public class SetupSkeleton : MonoBehaviour
{
    [Header("Wiring")]
    [Tooltip("Left empty, the receiver in the scene is found automatically.")]
    public PoseUdpReceiver receiver;
    [Tooltip("Avatar roots to hide while the setup skeleton is shown.")]
    public Transform[] avatarRoots;
    [Tooltip("Left empty, the ControlSender in the scene is found automatically.")]
    public ControlSender control;
    [Tooltip("Screens that must not be up before calibration — SetupScreen at " +
             "least. Re-enabled the moment the phase leaves CALIB.")]
    public GameObject[] hideWhileCalibrating;

    [Header("Look")]
    public Color colour = new Color(0.16f, 0.85f, 0.38f);
    public float jointRadius = 0.045f;
    public float boneRadius = 0.022f;

    [Header("Readout")]
    [Tooltip("The line on the card, while nothing is counting down.")]
    public string message = "Make sure all three cameras can see you";
    public string awaitingMessage = "Press Enter to start the countdown";
    public string countdownMessage = "Get into position";
    public string stepInMessage = "Step into view of all three cameras";
    public string holdStillMessage = "Calibrating - stand still and upright";
    [Tooltip("The camera counts, along the bottom. A stopgap until they are " +
             "bound into the setup screen's UXML.")]
    public bool showCameraCounts = true;
    [Tooltip("Size of the camera-count card relative to a 1080p screen; 1.25 matches the UI panels.")]
    public float cardScale = 1.25f;
    [Tooltip("Log what is actually arriving, once a second. Turn off when the " +
             "skeleton is behaving.")]
    public bool logDiagnostics = true;

    static readonly int[,] BONES = {
        {0,1},{0,2},{1,3},{2,4},
        {5,6},{5,11},{6,12},{11,12},
        {5,7},{7,9},{6,8},{8,10},
        {11,13},{13,15},{12,14},{14,16}
    };

    Transform[] _joints;
    Transform[] _bones;
    Renderer[] _avatarRenderers;
    bool _visible;
    string _title = "", _counts = "";
    float _nextLog;
    bool _awaiting, _sent;

    void Awake()
    {
        if (receiver == null) receiver = FindAnyObjectByType<PoseUdpReceiver>();
        if (control == null) control = FindAnyObjectByType<ControlSender>();
        var found = new System.Collections.Generic.List<Renderer>();
        if (avatarRoots != null)
            foreach (var root in avatarRoots)
                if (root != null)
                    found.AddRange(root.GetComponentsInChildren<Renderer>(true));
        _avatarRenderers = found.ToArray();
        if (transform.position != Vector3.zero
            || transform.rotation != Quaternion.identity
            || transform.localScale != Vector3.one)
        {
            Debug.Log($"[SetupSkeleton] resetting this object's transform from "
                      + $"{transform.position} so the skeleton lands at the origin.");
            transform.SetPositionAndRotation(Vector3.zero, Quaternion.identity);
            transform.localScale = Vector3.one;
        }
        Build();
        Show(false);
    }

    void Build()
    {
        Shader sh = Shader.Find("Unlit/Color");
        if (sh == null) sh = Shader.Find("Standard");
        var mat = new Material(sh) { color = colour };
        if (mat.HasProperty("_Color")) mat.SetColor("_Color", colour);

        _joints = new Transform[17];
        for (int i = 0; i < 17; i++)
            _joints[i] = Piece(PrimitiveType.Sphere, mat, $"joint{i:00}");
        _bones = new Transform[BONES.GetLength(0)];
        for (int b = 0; b < _bones.Length; b++)
            _bones[b] = Piece(PrimitiveType.Cylinder, mat, $"bone{b:00}");
    }

    Transform Piece(PrimitiveType kind, Material mat, string name)
    {
        var go = GameObject.CreatePrimitive(kind);
        go.name = name;
        var col = go.GetComponent<Collider>();
        if (col != null) Destroy(col);
        go.GetComponent<Renderer>().sharedMaterial = mat;
        go.transform.SetParent(transform, false);
        return go.transform;
    }

    void Update()
    {
        JSONNode pkt = receiver != null ? receiver.Latest : null;
        bool live = receiver != null && receiver.IsLive;
        bool calib = live && pkt != null && !pkt.IsNull
                     && pkt["phase"].Value == "CALIB";

        if (!calib) { Show(false); _title = _counts = ""; _sent = false; return; }

        Show(true);
        _awaiting = pkt["awaiting"].AsInt == 1;
        if (!_awaiting) _sent = false;
        if (_awaiting && !_sent && (Input.GetKeyDown(KeyCode.Return)
                                    || Input.GetKeyDown(KeyCode.KeypadEnter)))
        {
            if (control != null) { control.SendCalibrate(); _sent = true; }
            else Debug.LogWarning("[SetupSkeleton] no ControlSender - Enter cannot reach Python.");
        }
        Readout(pkt);

        JSONNode js = pkt["joints"];
        bool haveJoints = js != null && !js.IsNull && js.Count >= 17;
        bool present = pkt["present"].AsInt == 1 && haveJoints;
        for (int i = 0; i < 17; i++)
        {
            JSONNode j = present ? js[i] : null;
            bool ok = j != null && !j.IsNull && j.Count == 3;
            _joints[i].gameObject.SetActive(ok);
            if (ok)
                _joints[i].localPosition =
                    new Vector3(j[0].AsFloat, j[1].AsFloat, j[2].AsFloat);
            _joints[i].localScale = Vector3.one * (jointRadius * 2f);
        }

        for (int b = 0; b < _bones.Length; b++)
        {
            int i = BONES[b, 0], k = BONES[b, 1];
            bool ok = _joints[i].gameObject.activeSelf
                      && _joints[k].gameObject.activeSelf;
            Vector3 p = _joints[i].localPosition, q = _joints[k].localPosition;
            float len = ok ? (q - p).magnitude : 0f;
            ok = ok && len > 1e-4f;
            _bones[b].gameObject.SetActive(ok);
            if (!ok) continue;
            _bones[b].localPosition = (p + q) * 0.5f;
            _bones[b].localRotation = Quaternion.FromToRotation(Vector3.up, q - p);
            _bones[b].localScale = new Vector3(boneRadius, len * 0.5f, boneRadius);
        }

        if (logDiagnostics && Time.time >= _nextLog)
        {
            _nextLog = Time.time + 1f;
            int shown = 0;
            foreach (var t in _joints) if (t.gameObject.activeSelf) shown++;
            Debug.Log($"[SetupSkeleton] present={pkt["present"].AsInt}  " +
                      $"joints={(haveJoints ? js.Count.ToString() : "MISSING")}  " +
                      $"drawn={shown}/17  hip={_joints[11].position}  " +
                      $"cam={Camera.main?.transform.position}");
        }
    }

    void Readout(JSONNode pkt)
    {
        var s = new System.Text.StringBuilder();
        JSONNode cams = pkt["cams"];
        if (cams != null && !cams.IsNull)
            for (int i = 0; i < cams.Count; i++)
                s.Append($"cam{cams[i]["cam"].AsInt}   {cams[i]["n"].AsInt}/17        ");
        _counts = s.ToString().TrimEnd();
        JSONNode cd = pkt["countdown"];
        JSONNode nt = pkt["note"];
        string why = (nt == null || nt.IsNull) ? "" : nt.Value;
        if (_awaiting) _title = _sent ? "Starting…"
                              : string.IsNullOrEmpty(why) ? awaitingMessage
                              : why + " Press Enter to try again.";
        else if (cd != null && !cd.IsNull) _title = $"{countdownMessage} — {cd.AsInt}";
        else if (pkt["note"].Value == "step into view") _title = stepInMessage;
        else if (pkt["note"].Value == "hold still") _title = holdStillMessage;
        else _title = message;
    }

    void Show(bool on)
    {
        if (on == _visible) return;
        _visible = on;
        foreach (var t in _joints) t.gameObject.SetActive(false);
        foreach (var t in _bones) t.gameObject.SetActive(false);
        if (_avatarRenderers != null)
            foreach (var r in _avatarRenderers)
                if (r != null) r.enabled = !on;
        if (hideWhileCalibrating != null)
            foreach (var go in hideWhileCalibrating)
                if (go != null) go.SetActive(!on);
    }

    void OnGUI()
    {
        if (!showCameraCounts || !_visible || _title.Length == 0) return;

        float k = cardScale * Screen.height / 1080f;
        float lift = 34f * k, pad = 44f * k;
        float w = Mathf.Min(660f * k, Screen.width - 2f * pad);

        var title = new GUIStyle(GUI.skin.label)
        {
            fontSize = Mathf.RoundToInt(21 * k),
            fontStyle = FontStyle.Bold,
            alignment = TextAnchor.MiddleCenter,
            wordWrap = true
        };
        title.normal.textColor = new Color(0.04f, 0.04f, 0.04f);
        float inset = 24f * k;
        float th = Mathf.Max(30f * k, title.CalcHeight(new GUIContent(_title), w - 2f * inset));
        float h = 14f * k + th + 4f * k + 28f * k + 20f * k;
        var card = new Rect((Screen.width - w) * 0.5f,
                            Screen.height - h - lift, w, h);

        GUI.DrawTexture(card, Texture2D.whiteTexture, ScaleMode.StretchToFill,
                        true, 0f, new Color(1f, 1f, 1f, 0.96f),
                        Vector4.zero, new Vector4(14f, 14f, 14f, 14f) * k);
        GUI.Label(new Rect(card.x + inset, card.y + 14f * k, card.width - 2f * inset, th), _title, title);

        var counts = new GUIStyle(GUI.skin.label)
        {
            fontSize = Mathf.RoundToInt(17 * k),
            fontStyle = FontStyle.Bold,
            alignment = TextAnchor.MiddleCenter
        };
        counts.normal.textColor = new Color(0.2f, 0.2f, 0.22f);
        GUI.Label(new Rect(card.x, card.y + 18f * k + th, card.width, 28f * k), _counts, counts);
    }
}
