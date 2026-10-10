using UnityEngine;
using UnityEngine.UIElements;
using SimpleJSON;

[RequireComponent(typeof(UIDocument))]
public class SetupUIController : MonoBehaviour
{
    public PoseUdpReceiver receiver;
    public ScreenFlowController flow;

    UIDocument _doc;
    bool _stanceOk;
    VisualElement _root, _chips, _choices, _startCard, _holdCard, _holdFill, _panel;
    Button _avatarF, _avatarM;
    Label _repCount, _startTitle, _startMsg, _status;
    Toggle _reviewRep, _reviewSet, _numbers, _depth, _repCountToggle, _guideToggle;
    Button _minus, _plus, _gear, _close, _start, _resetCount;
    Label _setCountHelp;
    ScreenFlowController _flow;
    VisualElement _stepper;
    Label _repLabel, _repFixed;
    VisualElement _guideCard;
    Label _guideSideH, _guideNote;
    Button _guideBack, _guideReady;
    SquatGuideElement _guideSide;
    string _guideTarget;
    BarHoldDetector _barHold;

    void OnEnable()
    {
        _doc = GetComponent<UIDocument>();
        if (receiver == null) receiver = FindAnyObjectByType<PoseUdpReceiver>();
        if (flow == null) flow = FindAnyObjectByType<ScreenFlowController>();
        if (_barHold == null) _barHold = FindAnyObjectByType<BarHoldDetector>();
        _root = null;
    }

    T Get<T>(string name) where T : VisualElement
    {
        var e = _root.Q<T>(name);
        if (e == null) Debug.LogWarning($"[SetupUI] no element named '{name}' in the UXML.");
        return e;
    }

    bool Bind()
    {
        var root = _doc != null ? _doc.rootVisualElement : null;
        if (root == null) return false;
        if (root == _root) return true;
        _root = root;

        _root.style.flexGrow = 1;
        for (int i = 0; i < _root.childCount; i++)
        {
            var c = _root[i];
            c.style.position = Position.Absolute;
            c.style.left = 0; c.style.top = 0; c.style.right = 0; c.style.bottom = 0;
        }

        _choices     = Get<VisualElement>("choices");
        _chips       = Get<VisualElement>("target-chips");
        _repCount    = Get<Label>("rep-count");
        _minus       = Get<Button>("rep-minus");
        _plus        = Get<Button>("rep-plus");
        _start       = Get<Button>("start-button");
        _startCard   = Get<VisualElement>("start-card");
        _startTitle  = Get<Label>("start-title");
        _startMsg    = Get<Label>("start-msg");
        _holdCard    = Get<VisualElement>("hold-card");
        _holdFill    = Get<VisualElement>("hold-fill");
        _gear        = Get<Button>("settings-button");
        _panel       = Get<VisualElement>("settings-panel");
        _close       = Get<Button>("settings-close");
        _reviewRep      = Get<Toggle>("set-review-rep");
        _reviewSet      = Get<Toggle>("set-review-set");
        _numbers        = Get<Toggle>("set-numbers");
        _depth          = Get<Toggle>("set-depth");
        _repCountToggle = Get<Toggle>("set-repcount");
        _guideToggle    = Get<Toggle>("set-guide");
        _stepper        = Get<VisualElement>("rep-stepper");
        _resetCount     = Get<Button>("set-reset-count");
        _setCountHelp   = Get<Label>("set-count-help");
        _avatarF        = Get<Button>("set-avatar-f");
        _avatarM        = Get<Button>("set-avatar-m");
        if (_flow == null) _flow = FindAnyObjectByType<ScreenFlowController>();
        _repLabel       = Get<Label>("rep-label");
        _repFixed       = Get<Label>("rep-fixed");
        _status      = Get<Label>("status");
        _guideCard   = Get<VisualElement>("guide-card");
        _guideSideH  = Get<Label>("guide-side-h");
        _guideNote   = Get<Label>("guide-depth-note");
        _guideBack   = Get<Button>("guide-back");
        _guideReady  = Get<Button>("guide-ready");
        AddGuide(Get<VisualElement>("guide-front"), SquatGuideElement.View.Front);
        _guideSide   = AddGuide(Get<VisualElement>("guide-side"), SquatGuideElement.View.Side);
        _guideTarget = null;
        if (_guideBack != null)  _guideBack.clicked  += () => { if (flow != null) flow.BackToChoosing(); };
        if (_guideReady != null) _guideReady.clicked += () => { if (flow != null) flow.ConfirmBriefing(); };

        BuildChips();
        if (_minus != null) _minus.clicked += () => SessionSettings.RepTarget -= 1;
        if (_plus  != null) _plus.clicked  += () => SessionSettings.RepTarget += 1;
        if (_start != null) _start.clicked += () => { if (flow != null) flow.StartSet(); };
        if (_resetCount != null)
            _resetCount.clicked += () => { if (_flow != null) _flow.ResetSetCount(); };
        if (_gear  != null) _gear.clicked  += () => Show(_panel, true);
        if (_close != null) _close.clicked += () => Show(_panel, false);
        if (_reviewRep != null) _reviewRep.RegisterValueChangedCallback(e =>
        { if (e.newValue) SessionSettings.ReviewMode = SessionSettings.Review.PerRep; });
        if (_reviewSet != null) _reviewSet.RegisterValueChangedCallback(e =>
        { if (e.newValue) SessionSettings.ReviewMode = SessionSettings.Review.PerSet; });
        if (_avatarF != null)
            _avatarF.clicked += () => SessionSettings.AvatarChoice = SessionSettings.Avatar.Female;
        if (_avatarM != null)
            _avatarM.clicked += () => SessionSettings.AvatarChoice = SessionSettings.Avatar.Male;
        if (_numbers != null) _numbers.RegisterValueChangedCallback(e => SessionSettings.ShowNumbers = e.newValue);
        if (_depth != null) _depth.RegisterValueChangedCallback(e => SessionSettings.ShowDepthMargin = e.newValue);
        if (_repCountToggle != null) _repCountToggle.RegisterValueChangedCallback(e => SessionSettings.ShowRepCount = e.newValue);
        if (_guideToggle != null) _guideToggle.RegisterValueChangedCallback(e => SessionSettings.ShowSetupGuide = e.newValue);

        Refresh();
        Debug.Log("[SetupUI] bound to the visual tree.");
        return true;
    }

    /// Put a guide figure inside its host, filling it.
    static SquatGuideElement AddGuide(VisualElement host, SquatGuideElement.View view)
    {
        if (host == null) return null;
        var g = new SquatGuideElement(view, SessionSettings.DepthTarget);
        g.style.position = Position.Absolute;
        g.style.left = 0; g.style.top = 0; g.style.right = 0; g.style.bottom = 0;
        host.Add(g);
        return g;
    }

    /// Redraw the side view and its sentence when the depth target changes.
    void RefreshGuide()
    {
        string t = SessionSettings.DepthTarget;
        if (t == _guideTarget) return;
        _guideTarget = t;
        _guideSide?.SetTarget(t);
        if (_guideSideH != null) _guideSideH.text = "AT THE BOTTOM: " + t.ToUpper();
        if (_guideNote != null) _guideNote.text = SquatGuideElement.DepthCue(t);
    }

    /// One chip per entry in SessionSettings.Targets — generated, not authored, so adding a variation later means touching the settings list only.
    void BuildChips()
    {
        if (_chips == null) return;
        _chips.Clear();
        foreach (string t in SessionSettings.Targets)
        {
            string target = t;
            var chip = new Button(() => SessionSettings.DepthTarget = target)
            { text = char.ToUpper(target[0]) + target.Substring(1) };
            chip.AddToClassList("chip");
            chip.userData = target;
            _chips.Add(chip);
        }
    }

    /// Redraws everything that comes from settings rather than from the stream.
    void Refresh()
    {
        if (_repCount != null) _repCount.text = SessionSettings.RepTarget.ToString();
        if (_setCountHelp != null)
        {
            int done = _flow != null ? _flow.SetIndex : 0;
            _setCountHelp.text = done == 1 ? "1 set completed this session"
                               : $"{done} sets completed this session";
        }
        if (_chips != null)
            foreach (var c in _chips.Children())
                c.EnableInClassList("chip--on", (string)c.userData == SessionSettings.DepthTarget);
        if (_reviewRep != null) _reviewRep.SetValueWithoutNotify(SessionSettings.ReviewEachRep);
        if (_reviewSet != null) _reviewSet.SetValueWithoutNotify(SessionSettings.ReviewEachSet);
        if (_numbers != null) _numbers.SetValueWithoutNotify(SessionSettings.ShowNumbers);
        if (_depth != null) _depth.SetValueWithoutNotify(SessionSettings.ShowDepthMargin);
        if (_repCountToggle != null) _repCountToggle.SetValueWithoutNotify(SessionSettings.ShowRepCount);
        if (_guideToggle != null) _guideToggle.SetValueWithoutNotify(SessionSettings.ShowSetupGuide);
        bool male = SessionSettings.AvatarChoice == SessionSettings.Avatar.Male;
        _avatarF?.EnableInClassList("chip--on", !male);
        _avatarM?.EnableInClassList("chip--on", male);

        bool editable = SessionSettings.RepTargetEditable;
        Show(_stepper, editable);
        Show(_repFixed, !editable);
        if (_repLabel != null) _repLabel.text = editable ? "REPS IN THIS SET" : "REPS";
    }

    void Update()
    {
        if (!Bind()) return;
        Refresh();

        bool checking = flow != null && flow.Phase == ScreenFlowController.SetupPhase.Checking;
        bool briefing = flow != null && flow.Phase == ScreenFlowController.SetupPhase.Briefing;
        Show(_choices, !checking && !briefing);
        Show(_guideCard, briefing);
        Show(_startCard, checking);
        Show(_holdCard, checking);
        RefreshGuide();

        bool live = receiver != null && receiver.IsLive && receiver.Latest != null;
        if (_status != null)
            _status.text = live ? "connected" : "Waiting for data…";

        JSONNode stance = null;
        if (live)
        {
            JSONNode st = receiver.Latest["state"];
            if (st != null && !st.IsNull) stance = st["stance"];
        }
        _stanceOk = stance != null && !stance.IsNull && stance["class"].Value == "medium";
        DrawHold();
    }

    void DrawHold()
    {
        float p = flow != null ? flow.HoldProgress : 0f;
        if (_holdFill != null) _holdFill.style.height = Length.Percent(p * 100f);
        _startCard?.EnableInClassList("counting", p > 0f);
        _holdCard?.EnableInClassList("counting", p > 0f);

        if (_startTitle == null || _startMsg == null) return;
        if (flow != null && flow.ReferencesTimedOut)
        {
            _startTitle.text = "Let’s check your stance again";
            _startMsg.text = "Stand tall with your knees straight and hold still.";
        }
        else if (p <= 0f)
        {
            _startTitle.text = "Get into position";
            bool needBar = flow != null && flow.requireStance && flow.requireBarHold
                           && _barHold != null && !_barHold.Holding;
            _startMsg.text = !_stanceOk ? "Place your feet on the green circles."
                           : needBar ? "Hold the bar across your upper back with your elbows pointing down."
                           : "Stance width looks good.";
        }
        else
        {
            float left = flow != null ? Mathf.Max(0f, flow.holdSeconds * (1f - p)) : 0f;
            _startTitle.text = $"Starting in {Mathf.CeilToInt(left)}…";
            _startMsg.text = "Stand tall and hold still.";
        }
    }

    static void Show(VisualElement e, bool on) { if (e != null) e.EnableInClassList("hidden", !on); }
}
