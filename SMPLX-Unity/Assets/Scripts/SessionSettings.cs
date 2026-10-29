using System;
using UnityEngine;

public static class SessionSettings
{
    /// Raised whenever a setting changes.
    public static event Action Changed;

    const string K_TARGET = "sk.depthTarget";
    const string K_REPS   = "sk.repTarget";
    const string K_REVIEW = "sk.reviewMode";
    const string K_NUMS   = "sk.showNumbers";
    const string K_DEPTH  = "sk.showDepthMargin";
    const string K_RCOUNT = "sk.showRepCount";
    const string K_AVATAR = "sk.avatar";
    const string K_CLOTH  = "sk.clothing";
    const string K_GUIDE  = "sk.showSetupGuide";
    const string K_LIVE   = "sk.liveDepth";

    /// What the athlete stops to read.
    public enum Review { PerRep = 1, PerSet = 2 }

    /// Which character is displayed.
    public enum Avatar { Female = 1, Male = 2 }

    /// Live depth display options.
    public enum LiveDepth { Bar = 1, Trajectory = 2, Off = 3 }

    static string _target;
    static int _reps;
    static Review _review;
    static bool _numbers, _depth, _repCount, _guide;
    static Avatar _avatar;
    static LiveDepth _live;
    static int _cloth;
    static bool _loaded;

    public static readonly string[] Targets = { "partial", "parallel", "deep" };

    static void Load()
    {
        if (_loaded) return;
        _loaded = true;
        _target  = PlayerPrefs.GetString(K_TARGET, "parallel");
        _reps    = Mathf.Clamp(PlayerPrefs.GetInt(K_REPS, 8), 3, 20);
        int rv = PlayerPrefs.GetInt(K_REVIEW, (int)Review.PerSet);
        _review = (rv == (int)Review.PerRep) ? Review.PerRep : Review.PerSet;
        _numbers = PlayerPrefs.GetInt(K_NUMS, 1) == 1;
        _depth   = PlayerPrefs.GetInt(K_DEPTH, 1) == 1;
        _repCount = PlayerPrefs.GetInt(K_RCOUNT, 1) == 1;
        _guide    = PlayerPrefs.GetInt(K_GUIDE, 1) == 1;
        int ld = PlayerPrefs.GetInt(K_LIVE, 0);
        _live = ld == (int)LiveDepth.Trajectory ? LiveDepth.Trajectory : LiveDepth.Bar;
        if (ld == (int)LiveDepth.Off)
        {
            _depth = false;
            PlayerPrefs.SetInt(K_DEPTH, 0); PlayerPrefs.SetInt(K_LIVE, (int)LiveDepth.Bar); PlayerPrefs.Save();
        }
        int av = PlayerPrefs.GetInt(K_AVATAR, (int)Avatar.Female);
        _avatar = (av == (int)Avatar.Male) ? Avatar.Male : Avatar.Female;
        _cloth = Mathf.Max(0, PlayerPrefs.GetInt(K_CLOTH, 0));
    }

    static void Save(string key, string v) { PlayerPrefs.SetString(key, v); Commit(); }
    static void Save(string key, int v)    { PlayerPrefs.SetInt(key, v);    Commit(); }
    static void Commit() { PlayerPrefs.Save(); Changed?.Invoke(); }

    public static string DepthTarget
    {
        get { Load(); return _target; }
        set
        {
            Load();
            if (Array.IndexOf(Targets, value) < 0 || value == _target) return;
            _target = value; Save(K_TARGET, value);
        }
    }

    /// The repetition target, which is 1 while each rep is reviewed.
    public static int RepTarget
    {
        get { Load(); return _review == Review.PerRep ? 1 : _reps; }
        set
        {
            Load();
            if (_review == Review.PerRep) return;
            int v = Mathf.Clamp(value, 3, 20);
            if (v == _reps) return;
            _reps = v; Save(K_REPS, v);
        }
    }

    /// The stepper is meaningless while per-rep review forces the target to 1.
    public static bool RepTargetEditable { get { Load(); return _review != Review.PerRep; } }

    public static Review ReviewMode
    {
        get { Load(); return _review; }
        set
        {
            Load();
            if (value != Review.PerRep && value != Review.PerSet) return;
            if (value == _review) return;
            _review = value; Save(K_REVIEW, (int)value);
        }
    }

    public static Avatar AvatarChoice
    {
        get { Load(); return _avatar; }
        set
        {
            Load();
            if (value != Avatar.Female && value != Avatar.Male) return;
            if (value == _avatar) return;
            _avatar = value; Save(K_AVATAR, (int)value);
        }
    }

    /// Index into whatever colourways the scene offers for the chosen character.
    public static int ClothingIndex
    {
        get { Load(); return _cloth; }
        set
        {
            Load();
            int v = Mathf.Max(0, value);
            if (v == _cloth) return;
            _cloth = v; Save(K_CLOTH, v);
        }
    }

    public static bool ReviewEachRep => ReviewMode == Review.PerRep;
    public static bool ReviewEachSet => ReviewMode == Review.PerSet;

    public static bool ShowNumbers
    {
        get { Load(); return _numbers; }
        set { Load(); if (value == _numbers) return; _numbers = value; Save(K_NUMS, value ? 1 : 0); }
    }

    /// Whether the live screen shows depth.
    public static bool ShowDepthMargin
    {
        get { Load(); return _depth; }
        set { Load(); if (value == _depth) return; _depth = value; Save(K_DEPTH, value ? 1 : 0); }
    }

    /// How live depth is drawn when it is shown: the depth bar or the trajectory chart.
    public static LiveDepth DepthStyle
    {
        get { Load(); return _live; }
        set
        {
            Load();
            if (value != LiveDepth.Bar && value != LiveDepth.Trajectory) return;
            if (value == _live) return;
            _live = value; Save(K_LIVE, (int)value);
        }
    }

    /// What the live screen draws: Off when live depth is switched off, otherwise the chosen style.
    public static LiveDepth LiveDepthMode => ShowDepthMargin ? DepthStyle : LiveDepth.Off;

    public static bool ShowRepCount
    {
        get { Load(); return _repCount; }
        set { Load(); if (value == _repCount) return; _repCount = value; Save(K_RCOUNT, value ? 1 : 0); }
    }

    /// Whether Start opens the squat guide (feet, bar and depth) before the stance check.
    public static bool ShowSetupGuide
    {
        get { Load(); return _guide; }
        set { Load(); if (value == _guide) return; _guide = value; Save(K_GUIDE, value ? 1 : 0); }
    }
}
