

SESSION_TITLE = "Session {session}"
SESSION_SUB = "Summary of squat depth, technique and timing across all sets."
SESSION_SETS = "Sets"
SESSION_REPS = "Repetitions"
SESSION_FLAGGED = "Reps flagged"
SESSION_BLOCKS = "Blocks"
SESSION_DRIVER = "Count-in controlled by"
SESSION_CAPTURED = "Captured"
SESSION_RECORDING = "Recording"
BLOCK_HEADING = "Block {n}"


SET_TITLE_NUMBERED = "Set {idx}"
SET_SUBTITLE = "Set {idx} · {n} repetitions · {target} squat"
SET_SUB_ONE = "Set {idx} · 1 repetition · {target} squat"
SET_SUBTITLE_NUMBERED = "{n} repetitions · {target} squat"
SET_SUB_ONE_NUMBERED = "1 repetition · {target} squat"
SET_EMPTY = "{sub} — no repetitions recorded"


ALL_CLEAN = "No repetitions flagged"
ALL_CLEAN_BODY = (
    "Every rep met or exceeded your depth target, with no sustained inward knee movement detected."
)

SOME_FAULTS = "{k} of {n} repetitions flagged"
ONE_FAULT = "1 of {n} repetitions flagged"

FAULTS_BODY = "The results below show which repetitions were flagged and why."


DEPTH_ALL = "All repetitions on target"
DEPTH_ON_TARGET = "{k} / {n} repetitions on target"
DEPTH_NUM = "Average hip position: {v} mm above knee level"
DEPTH_BAND_LABEL = "{target} range"


VALGUS_NONE = "No sustained inward knee movement detected"
VALGUS_SOME = "{k} / {n} repetitions with sustained inward knee movement"
VALGUS_NUM = "Average inward knee movement in the {k} of {n} repetitions where the knees came inside the standing gap"
VALGUS_BIG_CAP = "average closest knee separation relative to standing (+ wider, \u2212 narrower)"

VALGUS_NUM_OUT = (
    "Knee separation remained at or above the standing reference "
    "in every repetition"
)

VALGUS_LEGEND = "Inward-movement limit ({v} mm)"

VALGUS_GAP_NOTE = (
    "No marker is shown when knee separation remained at or above "
    "the standing reference."
)


SYM_HEADING = "Average left–right knee flexion difference: {v}°"


SH_HEADING = "Average shoulder tilt: {v}° relative to standing"

SH_BAND_LABEL = "Within {v}°"

SH_NO_BASELINE = (
    "No standing shoulder reference was available for this set, so shoulder "
    "tilt is shown without baseline correction."
)


TEMPO_STATE = "Average tempo: {down} s down · {up} s up"
PAUSE_HEADING = "Bottom pause per rep"
PAUSE_COL = "Pause (s)"
REP_COL = "Rep"
TEMPO_DOWN = "Down"
TEMPO_UP = "Up"


CHART_H_DEPTH = "Hip position relative to knees (mm)"
CHART_H_VALGUS = "Knee separation relative to standing (mm)"
CHART_H_SYMMETRY = "Knee flexion difference (\u00b0)"
CHART_H_SHOULDERS = "Shoulder tilt relative to standing (\u00b0)"
CHART_H_TIMING = "Tempo"


SHOW_LEGEND = True

LEGEND_DEPTH = [
    ("band", "Target range"),
    ("green", "On target"),
    ("red", "Not deep enough"),
    ("amber", "Deeper than target"),
]

LEGEND_VALGUS = [
    ("dash", "Inward-movement limit"),
    ("red", "Sustained inward movement"),
    ("amber", "Brief inward movement"),
    ("green", "No sustained inward movement"),
]

LEGEND_SYMMETRY = [
    ("blue", "One repetition"),
]

LEGEND_SHOULDERS = [
    ("band", "Within {v}° of standing"),
    ("green", "Inside the band"),
    ("amber", "Outside the band"),
]


CARD_DEPTH = "DEPTH"
CARD_VALGUS = "KNEE TRACKING"
CARD_SYMMETRY = "KNEE SYMMETRY"
CARD_SHOULDERS = "SHOULDER ALIGNMENT"
CARD_TIMING = "TIMING"
CARD_REPS = "REPETITION DETAILS"


AX_X_TITLE = "Repetition"

AX_DEPTH = (
    "Shallower",
    "Knee level",
    "",
    "Deeper",
)

AX_VALGUS = (
    "Wider",
    "Standing reference",
    "",
    "Narrower",
)

AX_SYMMETRY = (
    "Right more flexed",
    "Equal flexion",
    "",
    "Left more flexed",
)

AX_SHOULDERS = (
    "Right higher",
    "Standing reference",
    "",
    "Left higher",
)


COL_REP = ("Rep", "")
COL_TARGET = ("Depth", "")
COL_MARGIN = ("Hip-knee", "mm")
COL_KNEE = ("Knee flex.", "°")
COL_VALGUS = ("Knee closure", "mm")
COL_VALGUS_SHARE = ("Inward movement", "%")
COL_SYM = ("Flexion diff.", "°")
COL_SHOULDER = ("Shoulder tilt", "°")
COL_DOWN = ("Descent", "s")
COL_PAUSE = ("Pause", "s")
COL_UP = ("Ascent", "s")
COL_FAULTS = ("Flags", "")


UNMEASURED = "Not measured"
NO_FAULTS = "—"

FOOTER = (
    "Report generated from the measurements recorded during this session."
)


CRUMB_SESSION = "Session"
CRUMB_SET = "Set {idx}"
REP_LABEL = "Rep {rep}"
BACK = "Back"
SHOW_ALL = "Show all charts"
SHOW_ONE = "Show one at a time"
SCOPE_SESSION = "Across {n} sets"
SCOPE_SET = "Across {n} repetitions"
MEASURES_H = "What this measures"
MATTERS_H = "What this tells you"
OPEN_SET_HINT = "Select a set to view its summary."

SESSION_EYEBROW = "Session summary"
SET_EYEBROW = "Set summary"
SESSION_SUB_LINE = "{sets} sets · {reps} repetitions · {date}"
SESSION_CLEAN = "No repetitions flagged"
SESSION_CLEAN_BODY = "Every rep in every set met or exceeded your depth target, with no sustained inward knee movement detected."
SESSION_SOME = "{k} of {n} sets had flagged repetitions"
SESSION_SOME_BODY = "Open a set to see which repetitions were flagged and why."
SET_ROW = "{target} · {n} reps"
SET_ROW_DEPTH = "{k} of {n} on target"

NAME_SETS = "Sets"
NAME_DEPTH = "Depth"
NAME_VALGUS = "Knee tracking"
NAME_SYMMETRY = "Knee symmetry"
NAME_SHOULDERS = "Shoulder alignment"
NAME_TIMING = "Timing"

PILL_ON_TARGET = "On target"
PILL_OFF_TARGET = "{k} off target"
PILL_FLAGGED = "{k} flagged"
PILL_ALL_CLEAR = "All clear"
PILL_REPORTED = "Reported"
PILL_BRIEF = "Brief"

CHART_H_DEPTH_SESSION = "Repetitions on target"
CHART_H_VALGUS_SESSION = "Repetitions with sustained inward knee movement"
CHART_H_TIMING_SESSION = "Average phase time (seconds)"
AX_X_SET = "Set"
SESSION_DEPTH_BIG = "repetitions on target across the session"
LEGEND_TOTAL_REPS = "Repetitions in the set"
SESSION_VALGUS_BIG = "repetitions with sustained inward knee movement"
CHART_H_SYMMETRY_SESSION = "Average knee flexion difference (\u00b0)"
CHART_H_SHOULDERS_SESSION = "Average shoulder tilt relative to standing (\u00b0)"
LEGEND_SET_AVG = "Set average"
LEGEND_RANGE = "Range across repetitions"

BIG_SYM_SET = "average left–right knee flexion difference across the set"
BIG_SH_SET = "average shoulder tilt relative to standing across the set"
BIG_TEMPO_SET = "average time down · up across the set"
BIG_SYM_SESSION = "average left–right knee flexion difference across the session"
BIG_SH_SESSION = "average shoulder tilt relative to standing across the session"
BIG_TEMPO_SESSION = "average time down · up across the session"

EXPLAIN = {
    "depth": {
        "session": ("Shows how many repetitions in each set reached the target depth.",
                    "Comparing sets shows whether depth held up, improved or dropped off as the session went on."),
        "set": ("Shows hip height relative to knee height near the bottom of each rep. The shaded band marks your selected depth range.",
                "See how consistently you reached your selected depth and which reps were shallower or deeper."),
    },
    "valgus": {
        "session": ("Counts the repetitions in each set where the knees moved inward beyond the limit for a sustained portion of the repetition.",
                    "Comparing sets shows whether inward knee movement appeared as the session went on, for example with fatigue."),
        "set": ("Measures the reduction in knee separation during each repetition relative to the standing reference. The dashed line indicates the limit used to identify excessive inward movement.",
                "See whether inward knee movement occurred in isolated reps or repeatedly across the set. Flagged reps show sustained movement beyond the limit."),
    },
    "symmetry": {
        "session": ("Shows the average left–right knee flexion difference for each set, with the range across its repetitions.",
                    "A difference that stays on the same side in every set is more likely to be a real asymmetry than one that changes from set to set."),
        "set": ("Compares left and right knee flexion, using the average difference between the two knee angles for each repetition.",
                "See whether the same knee tended to bend more across the set or whether the difference changed between reps."),
    },
    "shoulders": {
        "session": ("Shows the average shoulder tilt relative to standing for each set, with the range across its repetitions.",
                    "Each set has its own standing reference, so this compares how evenly the bar was carried in each set."),
        "set": ("Measures how far the shoulder line moves from your own standing shoulder line, recorded while you hold your stance before the set, averaged over each repetition. Zero means the shoulders are carried as they were at setup.",
                "See whether your shoulders tended to tilt further towards the same side across the set or whether the direction changed between reps."),
    },
    "timing": {
        "session": ("Shows the average descent and ascent time for each set.",
                    "Tempo is reported for reference. A slower ascent late in the session can be a sign of fatigue."),
        "set": ("Measures the average duration of the descent and ascent phases across the set, together with the bottom-pause duration of each repetition.",
                "Compare your average lowering and rising times with your intended pace, and check how consistently you paused at the bottom."),
    },
    "sets": {
        "session": ("Provides the full set summary for any set in the session.",
                    "The session charts compare sets. Opening a set shows its repetitions and charts."),
    },
}
