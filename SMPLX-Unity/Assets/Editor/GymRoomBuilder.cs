using UnityEngine;
using UnityEditor;
using System.IO;

public static class GymRoomBuilder
{
    const float ROOM_W = 6.0f, ROOM_D = 6.0f, ROOM_H = 3.0f;
    const float PLATFORM_L = 2.44f, PLATFORM_W = 1.22f, PLATFORM_T = 0.06f;

    const float STAND_W = 1.20f, STAND_H = 2.15f, TUBE = 0.075f;
    const float BASE_FWD = 0.75f, BASE_BACK = 0.35f;
    const float JHOOK_Y = 1.45f, SAFETY_Y = 0.95f, SAFETY_FWD = 0.50f;
    const float STAND_Z = -1.45f;

    const float BAR_L = 2.20f, BAR_R = 0.014f, SLEEVE_R = 0.025f, SLEEVE_L = 0.40f;
    const float PLATE_D = 0.450f, PLATE_T = 0.075f;

    const float DR_L = 1.60f, DR_D = 0.62f, DR_H = 0.90f;

    const string MAT_DIR = "Assets/Materials/Gym";

    [MenuItem("Tools/Skripsie/Build Gym Room")]
    public static void Build()
    {
        var existing = GameObject.Find("GymRoom");
        if (existing != null) Object.DestroyImmediate(existing);

        var floorMat  = Mat("GymFloor",  new Color(0.115f, 0.115f, 0.120f), 0.00f, 0.88f);
        var platMat   = Mat("GymPlatform", new Color(0.165f, 0.165f, 0.170f), 0.00f, 0.80f);
        var wallMat   = Mat("GymWall",   new Color(0.620f, 0.622f, 0.628f), 0.00f, 0.92f);
        var ceilMat   = Mat("GymCeiling", new Color(0.520f, 0.522f, 0.528f), 0.00f, 0.95f);
        var steelMat  = Mat("GymSteel",  new Color(0.085f, 0.088f, 0.095f), 0.45f, 0.40f);
        var chromeMat = Mat("GymChrome", new Color(0.780f, 0.790f, 0.800f), 0.90f, 0.15f);
        var rubberMat = Mat("GymRubber", new Color(0.060f, 0.060f, 0.065f), 0.00f, 0.93f);
        var mirrorMat = Mat("GymMirror", new Color(0.700f, 0.720f, 0.745f), 0.92f, 0.08f);

        var root = new GameObject("GymRoom");
        Undo.RegisterCreatedObjectUndo(root, "Build Gym Room");

        Box(root, "Floor",   new Vector3(0, -0.05f, 0), new Vector3(ROOM_W, 0.10f, ROOM_D), floorMat);
        Box(root, "Ceiling", new Vector3(0, ROOM_H + 0.05f, 0), new Vector3(ROOM_W, 0.10f, ROOM_D), ceilMat);
        Box(root, "Wall-Back",  new Vector3(0, ROOM_H / 2, -ROOM_D / 2), new Vector3(ROOM_W, ROOM_H, 0.10f), wallMat);
        Box(root, "Wall-Front", new Vector3(0, ROOM_H / 2,  ROOM_D / 2), new Vector3(ROOM_W, ROOM_H, 0.10f), wallMat);
        Box(root, "Wall-Left",  new Vector3(-ROOM_W / 2, ROOM_H / 2, 0), new Vector3(0.10f, ROOM_H, ROOM_D), wallMat);
        Box(root, "Wall-Right", new Vector3( ROOM_W / 2, ROOM_H / 2, 0), new Vector3(0.10f, ROOM_H, ROOM_D), wallMat);

        Box(root, "Skirt-Back",  new Vector3(0, 0.06f, -ROOM_D / 2 + 0.06f), new Vector3(ROOM_W, 0.12f, 0.02f), steelMat);
        Box(root, "Skirt-Left",  new Vector3(-ROOM_W / 2 + 0.06f, 0.06f, 0), new Vector3(0.02f, 0.12f, ROOM_D), steelMat);
        Box(root, "Skirt-Right", new Vector3( ROOM_W / 2 - 0.06f, 0.06f, 0), new Vector3(0.02f, 0.12f, ROOM_D), steelMat);

        Box(root, "Platform", new Vector3(0, -PLATFORM_T / 2 + 0.001f, 0),
            new Vector3(PLATFORM_L, PLATFORM_T, PLATFORM_W), platMat);

        BuildSquatStand(root, steelMat, chromeMat, rubberMat);

        var dr = BuildDumbbellRack(root, steelMat, rubberMat);
        dr.transform.localPosition = new Vector3(2.05f, 0f, -2.45f);
        dr.transform.localEulerAngles = new Vector3(0, -12f, 0);

        var plates = new GameObject("LoosePlates");
        plates.transform.SetParent(root.transform, false);
        for (int i = 0; i < 3; i++)
            Cyl(plates, $"Plate{i}",
                new Vector3(-2.35f + i * 0.11f, PLATE_D / 2, -ROOM_D / 2 + 0.38f),
                new Vector3(90, 0, 7),
                new Vector3(PLATE_D, PLATE_T / 2, PLATE_D), rubberMat);

        Box(root, "Mirror", new Vector3(-ROOM_W / 2 + 0.07f, 1.20f, 0.9f),
            new Vector3(0.03f, 1.80f, 2.40f), mirrorMat);
        Box(root, "Mirror-Frame", new Vector3(-ROOM_W / 2 + 0.06f, 1.20f, 0.9f),
            new Vector3(0.02f, 1.88f, 2.48f), steelMat);

        var lights = new GameObject("Lights");
        lights.transform.SetParent(root.transform, false);
        Lamp(lights, "Key",  new Vector3( 1.6f, 2.6f,  1.8f), 2.4f, 8f, new Color(1f, 0.97f, 0.93f));
        Lamp(lights, "Fill", new Vector3(-1.8f, 2.4f,  1.2f), 1.3f, 8f, new Color(0.91f, 0.94f, 1f));
        Lamp(lights, "Back", new Vector3( 0f,   2.7f, -2.2f), 1.6f, 7f, new Color(0.96f, 0.97f, 1f));

        Selection.activeGameObject = root;
        Debug.Log($"[GymRoomBuilder] built: room {ROOM_W}x{ROOM_D}x{ROOM_H} m, " +
                  $"squat stand {STAND_W} m inside x {STAND_H} m, platform " +
                  $"{PLATFORM_L}x{PLATFORM_W} m, dumbbell rack {DR_L}x{DR_D}x{DR_H} m. " +
                  "Delete GymRoom/SquatStand/RackedBarbell when the athlete gets her own bar.");
    }

    static void BuildSquatStand(GameObject parent, Material steel, Material chrome,
                                Material rubber)
    {
        var stand = new GameObject("SquatStand");
        stand.transform.SetParent(parent.transform, false);
        stand.transform.localPosition = new Vector3(0, 0, STAND_Z);
        float hx = STAND_W / 2 + TUBE / 2;

        foreach (float sx in new[] { -hx, hx })
        {
            string side = sx < 0 ? "L" : "R";
            Box(stand, $"Upright-{side}", new Vector3(sx, STAND_H / 2, 0),
                new Vector3(TUBE, STAND_H, TUBE), steel);
            Box(stand, $"Foot-{side}", new Vector3(sx, TUBE / 2, (BASE_FWD - BASE_BACK) / 2),
                new Vector3(TUBE, TUBE, BASE_FWD + BASE_BACK), steel);
            Box(stand, $"Post-{side}", new Vector3(sx, 0.16f, BASE_FWD - 0.05f),
                new Vector3(TUBE * 0.8f, 0.32f, TUBE * 0.8f), steel);
            Box(stand, $"JHook-{side}", new Vector3(sx, JHOOK_Y, 0.085f),
                new Vector3(TUBE * 0.9f, 0.05f, 0.17f), steel);
            Box(stand, $"JHookLip-{side}", new Vector3(sx, JHOOK_Y + 0.055f, 0.155f),
                new Vector3(TUBE * 0.9f, 0.11f, 0.03f), steel);
            Box(stand, $"Safety-{side}", new Vector3(sx, SAFETY_Y, SAFETY_FWD / 2),
                new Vector3(TUBE * 0.8f, TUBE * 0.8f, SAFETY_FWD), steel);
        }

        Cyl(stand, "PullupBar-Front", new Vector3(0, STAND_H - 0.06f, 0.10f),
            new Vector3(0, 0, 90), new Vector3(0.035f, STAND_W / 2 + TUBE, 0.035f), chrome);
        Cyl(stand, "PullupBar-Back", new Vector3(0, STAND_H - 0.06f, -0.14f),
            new Vector3(0, 0, 90), new Vector3(0.035f, STAND_W / 2 + TUBE, 0.035f), chrome);
        Box(stand, "TopPlate-L", new Vector3(-hx, STAND_H - 0.06f, -0.02f),
            new Vector3(TUBE, 0.10f, 0.30f), steel);
        Box(stand, "TopPlate-R", new Vector3( hx, STAND_H - 0.06f, -0.02f),
            new Vector3(TUBE, 0.10f, 0.30f), steel);

        var bb = new GameObject("RackedBarbell");
        bb.transform.SetParent(stand.transform, false);
        bb.transform.localPosition = new Vector3(0, JHOOK_Y + 0.04f, 0.085f);
        Cyl(bb, "Shaft", Vector3.zero, new Vector3(0, 0, 90),
            new Vector3(BAR_R * 2, BAR_L / 2, BAR_R * 2), chrome);
        foreach (float s in new[] { -1f, 1f })
        {
            Cyl(bb, s < 0 ? "Sleeve-L" : "Sleeve-R",
                new Vector3(s * (BAR_L / 2 - SLEEVE_L / 2), 0, 0), new Vector3(0, 0, 90),
                new Vector3(SLEEVE_R * 2, SLEEVE_L / 2, SLEEVE_R * 2), chrome);
            for (int i = 0; i < 2; i++)
                Cyl(bb, $"Plate-{(s < 0 ? "L" : "R")}{i}",
                    new Vector3(s * (BAR_L / 2 - SLEEVE_L + 0.06f + i * (PLATE_T + 0.005f)), 0, 0),
                    new Vector3(0, 0, 90),
                    new Vector3(PLATE_D, PLATE_T / 2, PLATE_D), rubber);
        }
    }

    static GameObject BuildDumbbellRack(GameObject parent, Material steel, Material rubber)
    {
        var rack = new GameObject("DumbbellRack");
        rack.transform.SetParent(parent.transform, false);

        float hx = DR_L / 2, hz = DR_D / 2;
        float[] tierY = { 0.22f, 0.52f, 0.82f };
        float[] tierZ = { hz - 0.16f, 0f, -hz + 0.16f };

        foreach (float sx in new[] { -hx, hx })
        {
            string side = sx < 0 ? "L" : "R";
            Box(rack, $"EndPost-Front-{side}", new Vector3(sx, 0.24f, hz - 0.05f),
                new Vector3(0.05f, 0.48f, 0.05f), steel);
            Box(rack, $"EndPost-Back-{side}", new Vector3(sx, DR_H / 2, -hz + 0.05f),
                new Vector3(0.05f, DR_H, 0.05f), steel);
            Box(rack, $"EndBrace-{side}", new Vector3(sx, 0.03f, 0),
                new Vector3(0.06f, 0.06f, DR_D), steel);
            var d = Box(rack, $"EndDiag-{side}", new Vector3(sx, 0.52f, 0.06f),
                new Vector3(0.04f, 0.86f, 0.04f), steel);
            d.transform.localEulerAngles = new Vector3(38f, 0, 0);
        }

        for (int t = 0; t < 3; t++)
        {
            Box(rack, $"Tier{t}-RailFront", new Vector3(0, tierY[t], tierZ[t] + 0.075f),
                new Vector3(DR_L, 0.045f, 0.045f), steel);
            Box(rack, $"Tier{t}-RailBack", new Vector3(0, tierY[t], tierZ[t] - 0.075f),
                new Vector3(DR_L, 0.045f, 0.045f), steel);

            int n = 5;
            float dScale = 1.0f - t * 0.16f;
            for (int i = 0; i < n; i++)
            {
                float x = -hx + 0.20f + i * ((DR_L - 0.40f) / (n - 1));
                Dumbbell(rack, $"DB-{t}-{i}",
                         new Vector3(x, tierY[t] + 0.085f * dScale, tierZ[t]),
                         dScale, steel, rubber);
            }
        }
        return rack;
    }

    static void Dumbbell(GameObject parent, string name, Vector3 pos, float s,
                         Material steel, Material rubber)
    {
        var g = new GameObject(name);
        g.transform.SetParent(parent.transform, false);
        g.transform.localPosition = pos;
        Cyl(g, "Handle", Vector3.zero, new Vector3(90, 0, 0),
            new Vector3(0.030f, 0.075f * s, 0.030f), chromeOr(steel));
        foreach (float e in new[] { -1f, 1f })
        {
            var head = Box(g, e < 0 ? "Head-A" : "Head-B",
                new Vector3(0, 0, e * 0.105f * s), new Vector3(0.15f * s, 0.15f * s, 0.09f * s), rubber);
            head.transform.localEulerAngles = new Vector3(0, 0, 45f);
        }
    }

    static Material chromeOr(Material m) => m;

    static GameObject Box(GameObject parent, string name, Vector3 pos, Vector3 size, Material m)
    {
        var g = GameObject.CreatePrimitive(PrimitiveType.Cube);
        g.name = name;
        g.transform.SetParent(parent.transform, false);
        g.transform.localPosition = pos;
        g.transform.localScale = size;
        g.GetComponent<Renderer>().sharedMaterial = m;
        Object.DestroyImmediate(g.GetComponent<Collider>());
        return g;
    }

    static GameObject Cyl(GameObject parent, string name, Vector3 pos, Vector3 euler,
                          Vector3 size, Material m)
    {
        var g = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
        g.name = name;
        g.transform.SetParent(parent.transform, false);
        g.transform.localPosition = pos;
        g.transform.localEulerAngles = euler;
        g.transform.localScale = size;
        g.GetComponent<Renderer>().sharedMaterial = m;
        Object.DestroyImmediate(g.GetComponent<Collider>());
        return g;
    }

    static void Lamp(GameObject parent, string name, Vector3 pos, float intensity,
                     float range, Color c)
    {
        var g = new GameObject(name);
        g.transform.SetParent(parent.transform, false);
        g.transform.localPosition = pos;
        var l = g.AddComponent<Light>();
        l.type = LightType.Point;
        l.intensity = intensity;
        l.range = range;
        l.color = c;
        l.shadows = LightShadows.Soft;
    }

    static Material Mat(string name, Color c, float metallic, float smoothInv)
    {
        Directory.CreateDirectory(MAT_DIR);
        string path = $"{MAT_DIR}/{name}.mat";
        var m = AssetDatabase.LoadAssetAtPath<Material>(path);
        if (m == null)
        {
            m = new Material(Shader.Find("Standard"));
            AssetDatabase.CreateAsset(m, path);
        }
        m.color = c;
        if (m.HasProperty("_Metallic"))   m.SetFloat("_Metallic", metallic);
        if (m.HasProperty("_Glossiness")) m.SetFloat("_Glossiness", 1f - smoothInv);
        EditorUtility.SetDirty(m);
        return m;
    }
}
