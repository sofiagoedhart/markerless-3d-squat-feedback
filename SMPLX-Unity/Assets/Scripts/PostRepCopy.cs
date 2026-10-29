public static class PostRepCopy
{
    public const string GoodRep = "Good repetition";

    public const string DepthOnTarget = "On target";
    public const string DepthShallow  = "Not deep enough";
    public const string DepthDeeper   = "Deeper than target";

    public const string KneeGood   = "No excessive inward knee movement";
    public const string KneeMostly = "Brief inward knee movement";

    public const string CueOkTitle    = "Within the knee-movement limit";
    public const string CueOkBody     = "Your knees stayed within the inward-movement limit during the assessed movement.";
    public const string CueBriefTitle = "Brief inward knee movement";
    public const string CueBriefBody  = "Your knees briefly moved closer together beyond the set limit.";
    public const string CueBadTitle   = "Sustained inward knee movement";
    public const string CueBadBody    = "Your knees moved inward beyond the limit for a sustained portion of the repetition. Aim to keep your knees aligned with the direction of your toes.";
    
    public const string CueWhen       = "Longest inward movement: {0:0.0} s during the {1}";
    public const string FaultValgus   = "Sustained inward knee movement";
    public const string CueHoldOne    = "Above the limit for {0:P0} of the repetition";
    public const string ChartXLabel   = "Time through repetition";
    public const string KneeZero     = " Standing reference";
    public const string ChartLimit    = "Inward-movement limit";
    public const string PhaseDescent  = "descent";
    public const string PhaseBottom   = "bottom";
    public const string PhaseAscent   = "ascent";

    public const string DepthBand   = "TARGET";

    public const string SymHeading = "Average knee flexion difference";
    public const string SymNum     = "{0:0.0}° · {1}";
    public const string SymEvenSide = "similar flexion on both sides";
    public const string SymSideL    = "left knee more flexed";
    public const string SymSideR    = "right knee more flexed";
    public const string ShHeading = "Average shoulder tilt relative to standing";
    public const string ShNum     = "{0:0.0}° · {1}";
    public const string ShZero    = "Standing reference";
    public const string ShBand    = "WITHIN {0:0}°";
    public const string ShNeither = "little average change from standing";
    public const string ShLeft    = "left shoulder higher";
    public const string ShRight   = "right shoulder higher";

    public const string TempoNum   = "{0:0.0} s down, {1:0.0} s up";
    public const string PauseNone  = "No pause";
    public const string PauseBrief = "Brief pause";
    public const string PauseHeld  = "Pause at the bottom";

    public const string FaultUnmeasured = "Depth could not be measured";
    public const string FaultOther      = "Technique fault identified";

    public const string RepTitle = "Rep {0}";
    public const string Subtitle = "Back squat · Target {0} · Reached {1}";

    /// The display word for an engine depth id.
    public static string DepthWord(string variation)
    {
        switch (variation)
        {
            case "too_shallow": return "too shallow";
            case "partial":     return "partial";
            case "parallel":    return "parallel";
            case "deep":        return "deep";
            default:            return variation;
        }
    }

    public const string StyleHip      = "Hip-driven";
    public const string StyleKnee     = "Knee-driven";
    public const string StyleBalanced = "Balanced";

    public const string PillOnTarget = "On target";
    public const string PillShallow  = "Not deep enough";
    public const string PillDeeper   = "Deeper than target";
    public const string PillSustained = "Sustained";
    public const string PillBrief    = "Brief";
    public const string PillReported = "Reported";
    public const string PillUnmeasured = "Not measured";
    public const string DepthOv      = "Target {0} · reached {1}";
    public const string DepthBig     = "{0:0} mm";
    public const string DepthBigCap  = "hip position above knee level · knee angle {0:0}°";
    public const string KneeBig      = "{0:+0;-0;0} mm";
    public const string KneeBigCap   = "closest knee separation relative to standing (+ wider, - narrower)";
    public const string DegBig       = "{0:0.0}°";
    public const string SymBigCap    = "average knee flexion difference · {0}";
    public const string ShBigCap     = "average shoulder tilt relative to standing · {0}";
    public const string StyleBigCap  = "upper-body lean minus shin lean {0:0}°";
    public const string BarSeconds   = "{0:0.0} s";
    public const string AxisSeconds  = "seconds";
    public const string PhaseKey3 = "The dashed vertical lines separate the three phases of the repetition.";
    public const string PhaseKey2 = "The dashed vertical line separates the descent from the ascent. There was no pause at the bottom.";
}
