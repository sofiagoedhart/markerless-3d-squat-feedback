using UnityEngine;
using SimpleJSON;

public class ScreenFlowController : MonoBehaviour
{
    public enum Screen { Setup, Live, PostRep, PostSet }

    /// The stages of the setup screen.
    public enum SetupPhase { Choosing, Briefing, Checking }

    [Header("Wiring")]
    public PoseUdpReceiver receiver;
    public GameObject setupScreen;
    public GameObject liveScreen;
    public GameObject postRepScreen;
    [Tooltip("The set summary. Shown when the set ends and 'review each set' is on.")]
    public GameObject postSetScreen;
    [Tooltip("Optional. Used to tell Python when Start is pressed.")]
    public ControlSender control;

    [Header("Starting the set")]
    [Tooltip("Seconds the stance must be held before the set starts (at least 4).")]
    public float holdSeconds = 5f;
    [Tooltip("Allow the squat guide between Start and the stance check.")]
    public bool showBriefing = true;
    [Tooltip("Require the bar hold before the count-in.")]
    public bool requireBarHold = true;
    [Tooltip("Left empty, found automatically.")]
    public BarHoldDetector barHold;
    [Tooltip("Require a medium stance before the count-in; off starts once a person is detected.")]
    public bool requireStance = true;

    [Header("Hand-off after a rep")]
    [Tooltip("Seconds to wait after the final rep before showing the rep card or set summary.")]
    public float reviewDelay = 2f;

    [Header("Post-rep card")]
    [Tooltip("Seconds before the card clears itself if nobody presses Done. " +
             "0 = wait for the user, which is the default.")]
    public float autoDismiss = 0f;
    [Tooltip("Screen that Done returns to from the rep card.")]
    public Screen whenDoneGoTo = Screen.Setup;
    [Tooltip("Close the rep card when the athlete starts the next rep.")]
    public bool dismissWhenMoving = false;

    public Screen Current { get; private set; } = Screen.Setup;
    public SetupPhase Phase { get; private set; } = SetupPhase.Choosing;
    /// Progress through the stance hold, from 0 to 1.
    public float HoldProgress { get; private set; }
    /// True briefly after a stance hold restarts because references were missing.
    public bool ReferencesTimedOut => Time.time < _refsFailedUntil;
    /// Number of sets completed this session.
    public int SetIndex { get; private set; }

    int _repSeen = -1;
    /// Index of the rep opened from the set summary, or -1.
    int _repFromSet = -1;
    int _session = -1;
    bool _pendingRestart;
    float _held, _postRepSince, _refsFailedUntil;
    /// When the delayed hand-off fires (Time.time), or -1 when none is waiting.
    float _handoffAt = -1f;
    bool _handoffEndsSet;

    void Start()
    {
        if (receiver == null) receiver = FindAnyObjectByType<PoseUdpReceiver>();
        if (control == null) control = FindAnyObjectByType<ControlSender>();
        if (barHold == null) barHold = FindAnyObjectByType<BarHoldDetector>();
        if (requireBarHold && barHold == null)
            Debug.LogWarning("[ScreenFlow] requireBarHold is on but there is no BarHoldDetector - ignoring it.");
        Show(Screen.Setup);
    }

    public void Show(Screen s)
    {
        Current = s;
        if (setupScreen != null)   setupScreen.SetActive(s == Screen.Setup);
        if (liveScreen != null)    liveScreen.SetActive(s == Screen.Live);
        if (postRepScreen != null) postRepScreen.SetActive(s == Screen.PostRep);
        if (postSetScreen != null) postSetScreen.SetActive(s == Screen.PostSet);
        if (s != Screen.PostRep) _repFromSet = -1;
        if (s == Screen.PostRep) _postRepSince = Time.time;
        _handoffAt = -1f;
        if (s == Screen.Setup) { _held = 0f; HoldProgress = 0f; Phase = SetupPhase.Choosing;
                                 _pendingRestart = false; }
        Debug.Log("[ScreenFlow] -> " + s);
    }

    /// Called by the Start button; opens the squat guide or the stance check.
    public void StartSet()
    {
        if (Current != Screen.Setup || Phase != SetupPhase.Choosing) return;
        if (showBriefing && SessionSettings.ShowSetupGuide) { Phase = SetupPhase.Briefing; Debug.Log("[ScreenFlow] start pressed -> guide"); }
        else ConfirmBriefing();
    }

    /// Called by the guide's Back button.
    public void BackToChoosing()
    {
        if (Current == Screen.Setup && Phase == SetupPhase.Briefing) Phase = SetupPhase.Choosing;
    }

    /// Called by the guide's ready button.
    public void ConfirmBriefing()
    {
        if (Current != Screen.Setup || Phase == SetupPhase.Checking) return;
        Phase = SetupPhase.Checking;
        _held = 0f; HoldProgress = 0f;
        if (barHold != null) barHold.ResetHold();
        if (receiver != null) receiver.ClearSet();
        Debug.Log("[ScreenFlow] guide confirmed -> stance check");
    }

    /// Open one rep of the finished set on the post-rep card.
    public void ShowRepFromSet(int index)
    {
        if (receiver == null || index < 0 || index >= receiver.SetReps.Count) return;
        _repFromSet = index;
        Show(Screen.PostRep);
    }

    /// True while the post-rep card shows a rep opened from the summary.
    public bool ReviewingFromSet => _repFromSet >= 0;

    /// Which rep the drill-down is showing, or -1.
    public int RepUnderReviewIndex => _repFromSet;

    /// The rep the drill-down is showing, or null.
    public JSONNode RepUnderReview =>
        (receiver != null && _repFromSet >= 0 && _repFromSet < receiver.SetReps.Count)
            ? receiver.SetReps[_repFromSet] : null;

    /// Called by the X on the post-rep card while it is showing a rep from the summary.
    public void BackToSet()
    {
        _repFromSet = -1;
        Show(Screen.PostSet);
    }

    /// Called by the post-rep screen's Done button.
    public void DismissPostRep()
    {
        if (Current != Screen.PostRep) return;
        if (_repFromSet >= 0) { BackToSet(); return; }
        Show(_pendingRestart ? Screen.Setup : whenDoneGoTo);
    }

    /// Called by the post-rep screen's "End set" button, and by Esc.
    public void EndSet()
    {
        _repSeen = receiver != null ? receiver.RepSequence : -1;
        bool anyReps = receiver != null && receiver.SetReps.Count > 0;
        if (control != null) control.SendEndSet();
        if (receiver != null) receiver.CloseSet();
        if (anyReps) SetIndex++;
        Show(SessionSettings.ReviewEachSet && anyReps ? Screen.PostSet : Screen.Setup);
    }

    /// Zero the completed-set counter.
    public void ResetSetCount() { SetIndex = 0; }

    /// Called by the post-set screen's Done button.
    public void DismissPostSet()
    {
        if (Current != Screen.PostSet) return;
        Show(Screen.Setup);
    }

    void Update()
    {
        if (Input.GetKeyDown(KeyCode.Escape) && Current != Screen.Setup)
        {
            if (Current == Screen.PostSet) Show(Screen.Setup);
            else if (_repFromSet >= 0) BackToSet();
            else EndSet();
            return;
        }

        JSONNode st = null;
        bool live = receiver != null && receiver.IsLive && receiver.Latest != null;
        if (live) st = receiver.Latest["state"];

        if (live)
        {
            int sess = receiver.Latest["session"].AsInt;
            if (_session < 0) _session = sess;
            else if (sess != _session)
            {
                _session = sess;
                _repSeen = -1;
                if (Current == Screen.PostRep || Current == Screen.PostSet) _pendingRestart = true;
                else if (Current != Screen.Setup) { Show(Screen.Setup); return; }
            }
        }

        switch (Current)
        {
            case Screen.Setup: TickSetup(live, st); break;
            case Screen.Live: TickLive(st); break;
            case Screen.PostRep: TickPostRep(st); break;
            case Screen.PostSet: TickPostSet(); break;
        }
    }

    void TickSetup(bool live, JSONNode st)
    {
        if (Phase != SetupPhase.Checking) { _held = 0f; HoldProgress = 0f; return; }

        bool ready = false;
        if (live && st != null && !st.IsNull)
        {
            if (!requireStance) ready = true;
            else
            {
                JSONNode stance = st["stance"];
                ready = stance != null && !stance.IsNull && stance["class"].Value == "medium";
            }
            if (requireStance && requireBarHold && barHold != null && !barHold.Holding) ready = false;
        }

        _held = ready ? _held + Time.deltaTime : 0f;
        HoldProgress = holdSeconds <= 0f ? (ready ? 1f : 0f) : Mathf.Clamp01(_held / holdSeconds);

        JSONNode rr = (live && st != null && !st.IsNull) ? st["refs_ready"] : null;
        bool refsReady = rr == null || rr.IsNull || rr.AsBool;
        if (HoldProgress >= 1f && !refsReady)
        {
            _held = 0f; HoldProgress = 0f;
            _refsFailedUntil = Time.time + 4f;
            Debug.Log("[ScreenFlow] stance references not ready at the end of the hold -> restarted");
        }

        if (HoldProgress >= 1f && refsReady)
        {
            _repSeen = receiver != null ? receiver.RepSequence : -1;
            if (receiver != null) receiver.ClearSet();
            if (control != null) control.SendStart();
            Show(Screen.Live);
        }
    }

    void TickLive(JSONNode st)
    {
        if (receiver == null) return;
        if (_repSeen < 0) _repSeen = receiver.RepSequence;

        if (_handoffAt >= 0f)
        {
            _repSeen = receiver.RepSequence;
            if (Time.time < _handoffAt) return;
            bool endsSet = _handoffEndsSet;
            _handoffAt = -1f;
            if (endsSet) EndSet(); else ShowRepCard();
            return;
        }

        if (receiver.RepSequence != _repSeen)
        {
            _repSeen = receiver.RepSequence;
            if (SessionSettings.ReviewEachRep) { Handoff(false); return; }

            Debug.Log($"[ScreenFlow] rep {receiver.SetReps.Count} of "
                      + $"{SessionSettings.RepTarget} collected");
            if (receiver.SetReps.Count >= SessionSettings.RepTarget)
            {
                receiver.CloseSet();
                Handoff(true);
                return;
            }
        }
    }

    /// Leave the live screen after reviewDelay seconds: to the rep card, or end the set.
    void Handoff(bool endsSet)
    {
        _handoffEndsSet = endsSet;
        if (reviewDelay <= 0f) { if (endsSet) EndSet(); else ShowRepCard(); return; }
        _handoffAt = Time.time + reviewDelay;
    }

    /// Opens the rep card.
    void ShowRepCard()
    {
        if (whenDoneGoTo == Screen.Setup)
        {
            if (control != null) control.SendEndSet();
            if (receiver != null) receiver.CloseSet();
        }
        Show(Screen.PostRep);
    }

    void TickPostRep(JSONNode st)
    {
        if (_repFromSet >= 0) return;
        if (dismissWhenMoving && st != null && !st.IsNull)
        {
            string phase = st["phase"].Value;
            if (!string.IsNullOrEmpty(phase) && phase != "SETUP") { Show(Screen.Live); return; }
        }
        if (autoDismiss > 0f && Time.time - _postRepSince > autoDismiss) Show(Screen.Live);
        if (receiver != null) _repSeen = receiver.RepSequence;
    }

    void TickPostSet()
    {
        if (receiver != null) _repSeen = receiver.RepSequence;
    }
}
