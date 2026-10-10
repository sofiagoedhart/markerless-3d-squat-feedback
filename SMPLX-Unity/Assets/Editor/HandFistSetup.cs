using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

public static class HandFistSetup
{
    /// Adds a HandFist to every SMPL-X avatar in the open scene, active or not.
    [MenuItem("Tools/Skripsie/Add Fists To Avatars")]
    static void AddFists()
    {
        int added = 0, found = 0;
        foreach (SMPLX s in Object.FindObjectsByType<SMPLX>(FindObjectsInactive.Include))
        {
            if (EditorUtility.IsPersistent(s)) continue;
            found++;
            if (s.GetComponent<HandFist>() != null) continue;
            Undo.AddComponent<HandFist>(s.gameObject);
            added++;
        }
        if (added > 0) EditorSceneManager.MarkSceneDirty(EditorSceneManager.GetActiveScene());
        Debug.Log($"[HandFist] {found} SMPL-X avatar(s) in the scene, fist added to {added}. Save the scene (⌘S).");
    }
}
