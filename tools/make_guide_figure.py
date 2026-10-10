"""Render the pre-set squat guide (SquatGuideElement.cs geometry) as one labelled PNG for sharing."""
import math
import textwrap
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

BODY, IRON, ACCENT, FLOOR = "#8f9cab", "#3a3b3f", "#2a78d6", "#c9c7c0"
INK, INK2, BG = "#1f2328", "#5b6470", "#fcfcfa"
CUES = {
    "partial": "Bend your hips and knees, keeping your hips above knee height.",
    "parallel": "Lower until your hip crease is level with the top of your knee.",
    "deep": "Lower until your hip crease is below the top of your knee.",
}
DPI = 200
plt.rcParams.update({"font.family": "DejaVu Sans"})


class Panel:
    """An axes in design units (y down) that converts design-unit line widths to points."""

    def __init__(self, fig, rect, W, H):
        self.ax = fig.add_axes(rect)
        self.ax.set_xlim(0, W); self.ax.set_ylim(H, 0)
        self.ax.set_aspect("equal"); self.ax.axis("off")
        fig.canvas.draw()
        bb = self.ax.get_window_extent()
        self.k = min(bb.width / W, bb.height / H) * 72 / DPI

    def seg(self, col, w, dashed, *pts, z=2):
        xs, ys = zip(*pts)
        self.ax.plot(xs, ys, color=col, lw=w * self.k, solid_capstyle="round", dash_capstyle="round",
                     solid_joinstyle="round", ls=(0, (4, 3)) if dashed else "-", zorder=z)

    def disc(self, col, at, r, z=3):
        self.ax.add_patch(plt.Circle(at, r, color=col, zorder=z))

    def ring(self, col, w, at, r):
        self.ax.add_patch(plt.Circle(at, r, fill=False, ec=col, lw=w * self.k, zorder=1))

    def arrow(self, a, b):
        self.seg(ACCENT, 2.5, False, a, b, z=4)
        d = ((b[0] - a[0]), (b[1] - a[1])); n = math.hypot(*d); d = (d[0] / n, d[1] / n); p = (-d[1], d[0])
        self.seg(ACCENT, 2.5, False, (b[0] - 8 * d[0] + 5 * p[0], b[1] - 8 * d[1] + 5 * p[1]), b,
                 (b[0] - 8 * d[0] - 5 * p[0], b[1] - 8 * d[1] - 5 * p[1]), z=4)

    def callout(self, text, x, y, width_chars, ha="left"):
        self.ax.text(x, y, textwrap.fill(text, width_chars), ha=ha, va="top", fontsize=8.6, color=INK,
                     linespacing=1.35, zorder=5,
                     bbox=dict(boxstyle="round,pad=0.45", fc="white", ec="#d9dde2", lw=0.8))


def front(fig, rect):
    P = Panel(fig, rect, 470, 310)
    V = lambda x, y: (x + 5, y)
    P.seg(FLOOR, 3, False, V(120, 288), V(340, 288))
    P.seg(IRON, 6, False, V(140, 84), V(320, 84))
    P.seg(IRON, 16, False, V(152, 60), V(152, 108)); P.seg(IRON, 16, False, V(308, 60), V(308, 108))
    P.seg(BODY, 34, False, V(230, 96), V(230, 158))
    P.seg(BODY, 11, False, V(208, 94), V(180, 128), V(176, 88))
    P.seg(BODY, 11, False, V(252, 94), V(280, 128), V(284, 88))
    P.seg(BODY, 15, False, V(220, 165), V(206, 218), V(198, 266))
    P.seg(BODY, 15, False, V(240, 165), V(254, 218), V(262, 266))
    P.seg(BODY, 10, False, V(198, 270), V(180, 281)); P.seg(BODY, 10, False, V(262, 270), V(280, 281))
    P.disc(BODY, V(230, 52), 17)
    P.arrow(V(176, 40), V(176, 72)); P.arrow(V(284, 40), V(284, 72))
    P.seg(ACCENT, 2.5, False, V(198, 298), V(262, 298))
    P.seg(ACCENT, 2.5, False, V(198, 293), V(198, 303)); P.seg(ACCENT, 2.5, False, V(262, 293), V(262, 303))
    P.seg(ACCENT, 1.5, True, V(338, 50), V(294, 70))
    P.seg(ACCENT, 1.5, True, V(118, 262), V(196, 298))
    P.arrow(V(338, 238), V(288, 277))
    P.callout("Pull the bar firmly against your upper back.", *V(340, 28), 18)
    P.callout("Place your feet slightly wider than shoulder width.", *V(4, 214), 17)
    P.callout("Point your toes slightly outwards.", *V(340, 214), 18)
    P.ax.text(*V(230, -14), "Setup (front view)", ha="center", va="bottom", fontsize=11, fontweight="bold", color=INK)


def side(fig, rect, target):
    P = Panel(fig, rect, 300, 330)
    knee, shin = {"partial": (101, 22), "parallel": (81, 30), "deep": (37, 36)}[target]
    SHIN, THIGH, TRUNK, LIMB, S_ = 0.42, 0.43, 0.50, 0.12, 200.0
    A = (0.0, 0.08)
    ps = math.radians(shin)
    K = (A[0] + SHIN * math.sin(ps), A[1] + SHIN * math.cos(ps))
    a = math.atan2(A[1] - K[1], A[0] - K[0])
    d = lambda t: (math.cos(t), math.sin(t))
    h1 = tuple(K[i] + THIGH * d(a + math.radians(knee))[i] for i in range(2))
    h2 = tuple(K[i] + THIGH * d(a - math.radians(knee))[i] for i in range(2))
    H = h1 if h1[0] < h2[0] else h2
    dx = max(-0.45, min(0.45, 0.05 - H[0]))
    lean = math.asin(dx / TRUNK)
    up = (math.sin(lean), math.cos(lean)); back = (-up[1], up[0])
    add = lambda p, q, k=1.0: (p[0] + k * q[0], p[1] + k * q[1])
    S = add(H, up, TRUNK)
    bar = add(add(S, back, 0.07), up, 0.03)
    head = add(add(S, up, 0.17), (0.03, 0.0))
    elbow = add(add(S, back, 0.10), up, -0.20)
    M = lambda p: (140 + p[0] * S_, 300 - p[1] * S_)
    kTop = K[1] + LIMB * 0.5
    P.seg(FLOOR, 3, False, M((-0.35, 0)), M((0.45, 0)))
    P.seg(ACCENT, 2, True, M((H[0] - 0.18, kTop)), M((K[0] + 0.14, kTop)), z=4)
    P.ring(FLOOR, 2.5, M(bar), 0.225 * S_)
    P.seg(BODY, 0.06 * S_, False, M((-0.05, 0.03)), M((0.19, 0.03)))
    P.seg(BODY, LIMB * S_, False, M(A), M(K), M(H))
    P.seg(BODY, 0.17 * S_, False, M(H), M(S))
    P.seg(BODY, 0.07 * S_, False, M(S), M(elbow), M(bar))
    P.disc(BODY, M(head), 0.10 * S_)
    P.disc(IRON, M(bar), 0.035 * S_, z=4)
    P.ax.text(150, -14, target.capitalize(), ha="center", va="bottom", fontsize=11, fontweight="bold", color=INK)
    P.ax.text(150, 312, textwrap.fill(CUES[target], 40), ha="center", va="top", fontsize=8.4, color=INK2, linespacing=1.35)


fig = plt.figure(figsize=(13.5, 4.4), dpi=DPI, facecolor=BG)
front(fig, [0.005, 0.20, 0.33, 0.70])
for i, t in enumerate(["partial", "parallel", "deep"]):
    side(fig, [0.35 + i * 0.215, 0.20, 0.20, 0.70], t)
fig.text(0.675, 0.03, "Side views: the dashed line marks the top of the knee. One depth is shown, matching the target chosen for the set.",
         ha="center", fontsize=8.4, color=INK2)
fig.savefig("squat_setup_guide.png", dpi=DPI, facecolor=BG)
print("ok")
