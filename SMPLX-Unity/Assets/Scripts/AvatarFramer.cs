using UnityEngine;

[RequireComponent(typeof(Camera))]
[ExecuteAlways]
public class AvatarFramer : MonoBehaviour
{
    [Header("Target")]
    [Tooltip("The avatar root. Left empty, the SMPLXPoseDriver's avatarRoot is used.")]
    public Transform target;
    [Tooltip("Where the athlete stands. The camera aims here, NOT at the moving avatar.")]
    public Vector3 anchor = Vector3.zero;

    [Header("Framing")]
    [Tooltip("Standing height of the athlete, metres. Only used to solve the distance.")]
    public float subjectHeight = 1.70f;
    [Range(0.3f, 1.0f)]
    [Tooltip("Fraction of the screen height the standing athlete fills (0.75-0.85 works well).")]
    public float fillFraction = 0.80f;
    [Tooltip("Height the camera aims at, as a fraction of standing height (about 0.55).")]
    [Range(0f, 1f)] public float aimHeightFraction = 0.55f;

    [Header("Angle")]
    [Tooltip("Place the camera in front of the avatar, using its hips to find which way it faces.")]
    public bool faceFromAvatar = true;
    [Tooltip("Reverse the facing direction for a rig built facing the other way.")]
    public bool flipFacing = false;
    [Tooltip("Camera angle around the athlete in degrees; 0 is straight in front.")]
    [Range(-180f, 180f)] public float yawDeg = 0f;
    [Tooltip("Degrees above the athlete. Small is better - a high camera " +
             "foreshortens the squat and makes depth hard to judge.")]
    [Range(-20f, 40f)] public float pitchDeg = 4f;

    [Header("Screen position")]
    [Tooltip("Sideways shift of the athlete in screen widths; positive moves right.")]
    [Range(-0.4f, 0.4f)] public float horizontalOffset = 0.14f;

    Camera _cam;
    Vector3 _lastSolve;

    void OnEnable()  { _cam = GetComponent<Camera>(); Reframe(); }
    void OnValidate() { _cam = GetComponent<Camera>(); if (_cam) Reframe(); }

    void Start()
    {
        if (target == null)
        {
            var drv = FindAnyObjectByType<SMPLXPoseDriver>();
            if (drv != null) target = drv.avatarRoot;
        }
        Reframe();
        Invoke(nameof(Start2Frame), 0f);
    }

    void Start2Frame() { Reframe(); }

    [ContextMenu("Reframe Now")]
    public void Reframe()
    {
        if (_cam == null) _cam = GetComponent<Camera>();
        if (_cam == null || _cam.orthographic) return;

        float half = Mathf.Max(subjectHeight, 0.1f) * 0.5f;
        float tan = Mathf.Tan(_cam.fieldOfView * 0.5f * Mathf.Deg2Rad);
        float dist = half / Mathf.Max(tan, 1e-4f) / Mathf.Clamp(fillFraction, 0.05f, 1f);

        Vector3 aim = anchor + Vector3.up * (subjectHeight * aimHeightFraction);

        float baseYaw = 0f;
        if (faceFromAvatar && target != null)
        {
            Transform lh = FindDeep(target, "left_hip"), rh = FindDeep(target, "right_hip");
            Transform pv = FindDeep(target, "pelvis"),   sp = FindDeep(target, "spine3");
            if (lh && rh && pv && sp)
            {
                Vector3 right = (rh.position - lh.position).normalized;
                Vector3 up = (sp.position - pv.position).normalized;
                up = (up - Vector3.Dot(up, right) * right).normalized;
                Vector3 fwd = Vector3.Cross(up, right);
                if (flipFacing) fwd = -fwd;
                fwd.y = 0f;
                if (fwd.sqrMagnitude > 1e-6f)
                    baseYaw = Quaternion.LookRotation(fwd.normalized, Vector3.up).eulerAngles.y;
            }
        }

        Quaternion rot = Quaternion.Euler(pitchDeg, baseYaw + yawDeg, 0f);
        Vector3 back = rot * Vector3.forward;
        transform.position = aim - back * dist;
        transform.rotation = Quaternion.LookRotation(back, Vector3.up);

        if (Mathf.Abs(horizontalOffset) > 1e-4f)
        {
            float halfW = tan * _cam.aspect * dist;
            float ang = Mathf.Atan2(halfW * 2f * horizontalOffset, dist) * Mathf.Rad2Deg;
            transform.rotation = Quaternion.AngleAxis(-ang, Vector3.up) * transform.rotation;
        }
        _lastSolve = transform.position;
    }

    static Transform FindDeep(Transform root, string name)
    {
        if (root == null) return null;
        foreach (Transform t in root.GetComponentsInChildren<Transform>(true))
            if (t.name == name) return t;
        return null;
    }

    void OnDrawGizmosSelected()
    {
        Gizmos.color = new Color(0.2f, 0.8f, 1f, 0.9f);
        Gizmos.DrawWireSphere(anchor, 0.05f);
        Gizmos.DrawLine(anchor, anchor + Vector3.up * subjectHeight);
        Gizmos.DrawLine(_lastSolve, anchor + Vector3.up * (subjectHeight * aimHeightFraction));
    }
}
