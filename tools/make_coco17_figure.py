"""Draw the colour-coded COCO-17 keypoint map for the thesis (front view, subject's left on image right)."""
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Ellipse, FancyBboxPatch, Rectangle

BG, CARD, EDGE = "white", "#f8fafc", "#e2e8f0"
TEXT, MUTED, BODY = "#1e293b", "#64748b", "#eef2f7"
CAT = {"Face": "#7c3aed", "Arms": "#d97706", "Torso": "#0d9488", "Legs": "#db2777"}

NAMES = ["Nose", "Left Eye", "Right Eye", "Left Ear", "Right Ear", "Left Shoulder", "Right Shoulder",
         "Left Elbow", "Right Elbow", "Left Wrist", "Right Wrist", "Left Hip", "Right Hip",
         "Left Knee", "Right Knee", "Left Ankle", "Right Ankle"]
CATS = ["Face"] * 5 + ["Torso"] * 2 + ["Arms"] * 4 + ["Torso"] * 2 + ["Legs"] * 4
PTS = {0: (226, 200), 1: (241, 182), 2: (211, 182), 3: (261, 197), 4: (191, 197),
       5: (264, 265), 6: (188, 265), 7: (291, 336), 8: (161, 336), 9: (316, 411), 10: (136, 411),
       11: (247, 411), 12: (205, 411), 13: (252, 502), 14: (200, 502), 15: (256, 582), 16: (196, 582)}
BONES = [(5, 6, "Torso"), (5, 11, "Torso"), (6, 12, "Torso"), (11, 12, "Torso"),
         (5, 7, "Arms"), (7, 9, "Arms"), (6, 8, "Arms"), (8, 10, "Arms"),
         (11, 13, "Legs"), (13, 15, "Legs"), (12, 14, "Legs"), (14, 16, "Legs")]

W, Y0, Y1 = 905, 94, 634
H = Y1 - Y0
fig = plt.figure(figsize=(W / 100, H / 100), facecolor=BG)
ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(20, 20 + W); ax.set_ylim(Y1, Y0); ax.axis("off")

ax.add_patch(Ellipse((226, 193), 72, 80, fc=BODY, ec="none"))
ax.add_patch(Rectangle((188, 265), 76, 146, fc=BODY, ec="none"))
ax.add_patch(Rectangle((205, 411), 20, 176, fc=BODY, ec="none"))
ax.add_patch(Rectangle((230, 411), 20, 176, fc=BODY, ec="none"))

for a, b, c in BONES:
    (x1, y1), (x2, y2) = PTS[a], PTS[b]
    ax.plot([x1, x2], [y1, y2], color=CAT[c], lw=2.2, alpha=0.75, solid_capstyle="round", zorder=2)
ax.plot([PTS[3][0], PTS[1][0], PTS[0][0], PTS[2][0], PTS[4][0]],
        [PTS[3][1], PTS[1][1], PTS[0][1], PTS[2][1], PTS[4][1]], color=CAT["Face"], lw=1.4, alpha=0.6, zorder=2)

order = [3, 4, 1, 2, 0] + list(range(5, 17))
for i in order:
    x, y = PTS[i]; col = CAT[CATS[i]]; r = 9.5 if i < 5 else 11.5
    ax.add_patch(Circle((x, y), r, fc=col, ec="white", lw=1.2, zorder=3))
    ax.text(x, y + 0.5, str(i), color="white", fontsize=6.5 if i < 5 else 7.5,
            fontweight="bold", ha="center", va="center", zorder=4)

ax.text(226, 618, "front view — subject's left is on the image right", color=MUTED, fontsize=7,
        ha="center", va="center", style="italic")

for i, name in enumerate(NAMES):
    cx = 446 if i % 2 == 0 else 670; cy = 110 + (i // 2) * 56
    col = CAT[CATS[i]]
    ax.add_patch(FancyBboxPatch((cx, cy), 215, 47, boxstyle="round,pad=0,rounding_size=6",
                                fc=CARD, ec=EDGE, lw=1))
    ax.add_patch(Rectangle((cx, cy + 6), 3, 35, fc=col, ec="none"))
    ax.add_patch(Circle((cx + 26, cy + 23.5), 12, fc=col, ec="none"))
    ax.text(cx + 26, cy + 24, str(i), color="white", fontsize=8, fontweight="bold", ha="center", va="center")
    ax.text(cx + 49, cy + 24, name, color=TEXT, fontsize=10, va="center")

out = "figures/coco17_keypoints"
fig.savefig(out + ".pdf", facecolor=BG)
fig.savefig(out + ".png", dpi=300, facecolor=BG)
print("saved", out)
