using UnityEngine;

[ExecuteAlways]
[DisallowMultipleComponent]
public class HandFist : MonoBehaviour
{
    [Tooltip("0 = flat hand, 1 = full fist. Scales the four fingers.")]
    [Range(0f, 1f)] public float fingerCurl = 1f;

    [Tooltip("0 = thumb straight, 1 = thumb pressed against the index finger.")]
    [Range(0f, 1f)] public float thumbCurl = 1f;

    static readonly string[] FINGERS = { "index", "middle", "pinky", "ring", "thumb" };

    static readonly float[] LEFT_FIST = {
        0f, 0f, -1.222f,   0f, 0f, -1.658f,   0f, 0f, -0.960f,
        0f, 0f, -1.361f,   0f, 0f, -1.710f,   0f, 0f, -0.960f,
        0f, 0f, -1.571f,   0f, 0f, -1.658f,   0f, 0f, -0.873f,
        0f, 0f, -1.466f,   0f, 0f, -1.710f,   0f, 0f, -0.908f,
        -0.667f, 0.690f, -0.350f,   0f, 0f, 0f,   0.355f, 0.358f, -0.358f,
    };

    Transform[] _left, _right;
    SMPLX _smplx;
    bool _dirty = true, _correctivesPending = true;

    void OnEnable() { _left = null; _correctivesPending = true; Apply(); }

    void OnDisable() { SetFlat(); }

    void OnValidate() { _dirty = _correctivesPending = true; }

    void Update()
    {
        if (!Application.isPlaying && _dirty) Apply();
    }

    void LateUpdate()
    {
        if (!Application.isPlaying) return;
        Apply();
        if (_correctivesPending && _smplx != null) _smplx.UpdatePoseCorrectives();
        _correctivesPending = false;
    }

    /// Writes the fist rotations onto all 30 finger bones.
    public void Apply()
    {
        if (!Bind()) return;
        for (int i = 0; i < 15; i++)
        {
            float k = i >= 12 ? thumbCurl : fingerCurl;
            float x = LEFT_FIST[i * 3] * k, y = LEFT_FIST[i * 3 + 1] * k, z = LEFT_FIST[i * 3 + 2] * k;
            _left[i].localRotation = SMPLX.QuatFromRodrigues(x, y, z);
            _right[i].localRotation = SMPLX.QuatFromRodrigues(x, -y, -z);
        }
        _dirty = false;
    }

    void SetFlat()
    {
        if (!Bind()) return;
        for (int i = 0; i < 15; i++) _left[i].localRotation = _right[i].localRotation = Quaternion.identity;
        _dirty = true;
    }

    bool Bind()
    {
        if (_left != null) return true;
        var byName = new System.Collections.Generic.Dictionary<string, Transform>();
        foreach (Transform t in GetComponentsInChildren<Transform>(true)) byName[t.name] = t;
        var l = new Transform[15];
        var r = new Transform[15];
        for (int f = 0; f < 5; f++)
            for (int j = 0; j < 3; j++)
            {
                string n = FINGERS[f] + (j + 1);
                if (!byName.TryGetValue("left_" + n, out l[f * 3 + j]) || !byName.TryGetValue("right_" + n, out r[f * 3 + j]))
                {
                    Debug.LogWarning($"[HandFist] no finger bone '{n}' under {name} - is this an SMPL-X root?", this);
                    return false;
                }
            }
        _left = l; _right = r;
        _smplx = GetComponentInChildren<SMPLX>(true);
        return true;
    }
}
