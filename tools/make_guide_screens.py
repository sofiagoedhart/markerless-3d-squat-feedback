"""Render the Unity setup-guide card (SquatGuideElement.cs + SetupUI.uss) at each depth target as vector PDFs."""
import math
import os
import sys

from playwright.sync_api import sync_playwright

BODY, IRON, ACCENT, FLOOR = "#8f9cab", "#3a3b3f", "#2a78d6", "#c9c7c0"
CUE_BAR = "Pull the bar firmly against your upper back."
CUE_FEET = "Place your feet slightly wider than shoulder width."
CUE_TOES = "Point your toes slightly outwards."
DEPTH_CUE = {
    "partial": "Bend your hips and knees, keeping your hips above knee height.",
    "parallel": "Lower until your hip crease is level with the top of your knee.",
    "deep": "Lower until your hip crease is below the top of your knee.",
}


class Fig:
    """Collects the same draw commands as SquatGuideElement and writes them as SVG."""

    def __init__(self, w, h):
        self.w, self.h, self.svg, self.labels = w, h, [], []

    def seg(self, col, w, dashed, *pts):
        d = "M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in pts)
        dash = ' stroke-dasharray="6 5"' if dashed else ""
        self.svg.append(f'<path d="{d}" fill="none" stroke="{col}" stroke-width="{w:.2f}" '
                        f'stroke-linecap="round" stroke-linejoin="round"{dash}/>')

    def disc(self, col, at, r):
        self.svg.append(f'<circle cx="{at[0]:.2f}" cy="{at[1]:.2f}" r="{r:.2f}" fill="{col}"/>')

    def ring(self, col, w, at, r):
        pts = [(at[0] + r * math.cos(i * math.pi / 16), at[1] + r * math.sin(i * math.pi / 16)) for i in range(33)]
        self.seg(col, w, False, *pts)

    def arrow(self, a, b):
        self.seg(ACCENT, 2.5, False, a, b)
        n = math.hypot(b[0] - a[0], b[1] - a[1]); d = ((b[0] - a[0]) / n, (b[1] - a[1]) / n); p = (-d[1], d[0])
        self.seg(ACCENT, 2.5, False, (b[0] - 8 * d[0] + 5 * p[0], b[1] - 8 * d[1] + 5 * p[1]), b,
                 (b[0] - 8 * d[0] - 5 * p[0], b[1] - 8 * d[1] - 5 * p[1]))

    def callout(self, text, x, y, w):
        self.labels.append(f'<div class="guide-callout" style="left:{100*x/self.w:.3f}%;top:{100*y/self.h:.3f}%;'
                           f'width:{100*w/self.w:.3f}%">{text}</div>')

    def html(self, cls):
        return (f'<div class="guide-fig {cls}"><svg viewBox="0 0 {self.w} {self.h}">{"".join(self.svg)}</svg>'
                f'{"".join(self.labels)}</div>')


def front():
    F = Fig(460, 300)
    F.seg(FLOOR, 3, False, (120, 288), (340, 288))
    F.seg(IRON, 6, False, (140, 84), (320, 84))
    F.seg(IRON, 16, False, (152, 60), (152, 108)); F.seg(IRON, 16, False, (308, 60), (308, 108))
    F.seg(BODY, 34, False, (230, 96), (230, 158))
    F.seg(BODY, 11, False, (208, 94), (180, 128), (176, 88))
    F.seg(BODY, 11, False, (252, 94), (280, 128), (284, 88))
    F.seg(BODY, 15, False, (220, 165), (206, 218), (198, 266))
    F.seg(BODY, 15, False, (240, 165), (254, 218), (262, 266))
    F.seg(BODY, 10, False, (198, 270), (180, 281)); F.seg(BODY, 10, False, (262, 270), (280, 281))
    F.disc(BODY, (230, 52), 17)
    F.arrow((176, 40), (176, 72)); F.arrow((284, 40), (284, 72))
    F.seg(ACCENT, 2.5, False, (198, 296), (262, 296))
    F.seg(ACCENT, 2.5, False, (198, 291), (198, 300)); F.seg(ACCENT, 2.5, False, (262, 291), (262, 300))
    F.seg(ACCENT, 1.5, True, (334, 48), (292, 54))
    F.seg(ACCENT, 1.5, True, (126, 252), (196, 292))
    F.arrow((334, 238), (288, 277))
    F.callout(CUE_BAR, 336, 30, 124); F.callout(CUE_FEET, 0, 222, 124); F.callout(CUE_TOES, 336, 222, 124)
    return F


def side(target):
    F = Fig(300, 300)
    knee, shin = {"partial": (101, 22), "deep": (37, 36)}.get(target, (81, 30))
    SHIN, THIGH, TRUNK, LIMB, SC = 0.42, 0.43, 0.50, 0.12, 200.0
    A = (0.0, 0.08); ps = math.radians(shin)
    K = (A[0] + SHIN * math.sin(ps), A[1] + SHIN * math.cos(ps))
    a = math.atan2(A[1] - K[1], A[0] - K[0])
    d = lambda t: (math.cos(t), math.sin(t))
    h1 = (K[0] + THIGH * d(a + math.radians(knee))[0], K[1] + THIGH * d(a + math.radians(knee))[1])
    h2 = (K[0] + THIGH * d(a - math.radians(knee))[0], K[1] + THIGH * d(a - math.radians(knee))[1])
    H = h1 if h1[0] < h2[0] else h2
    dx = max(-0.45, min(0.45, 0.05 - H[0])); lean = math.asin(dx / TRUNK)
    up = (math.sin(lean), math.cos(lean)); back = (-up[1], up[0])
    add = lambda p, q, k=1.0: (p[0] + k * q[0], p[1] + k * q[1])
    S = add(H, up, TRUNK)
    bar = add(add(S, back, 0.07), up, 0.03)
    head = add(add(S, up, 0.17), (0.03, 0.0))
    elbow = add(add(S, back, 0.10), up, -0.20)
    M = lambda p: (140 + p[0] * SC, 285 - p[1] * SC)
    kTop = K[1] + LIMB * 0.5
    F.seg(FLOOR, 3, False, M((-0.35, 0)), M((0.45, 0)))
    F.seg(ACCENT, 2, True, M((H[0] - 0.18, kTop)), M((K[0] + 0.14, kTop)))
    F.ring(FLOOR, 2.5, M(bar), 0.225 * SC)
    F.seg(BODY, 0.06 * SC, False, M((-0.05, 0.03)), M((0.19, 0.03)))
    F.seg(BODY, LIMB * SC, False, M(A), M(K), M(H))
    F.seg(BODY, 0.17 * SC, False, M(H), M(S))
    F.seg(BODY, 0.07 * SC, False, M(S), M(elbow), M(bar))
    F.disc(BODY, M(head), 0.10 * SC)
    F.disc(IRON, M(bar), 0.035 * SC)
    return F


CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Liberation Sans', Arial, sans-serif; background: #fff; }
.card { background: rgb(252,252,251); border-radius: 20px; border: 1px solid rgba(11,11,11,0.10);
        padding: 26px 34px; width: max-content; }
.guide-title { font-size: 30px; font-weight: bold; color: rgb(11,11,11); }
.guide-sub { font-size: 17px; color: rgb(82,81,78); margin: 4px 0 14px; }
.guide-row { display: flex; align-items: flex-start; }
.guide-panel-side { margin-left: 32px; width: 360px; }
.card-label { font-size: 14px; letter-spacing: 2px; color: rgb(82,81,78); font-weight: bold; }
.guide-fig { position: relative; margin-top: 8px; }
.guide-fig svg { position: absolute; inset: 0; width: 100%; height: 100%; }
.guide-fig-front { width: 552px; height: 360px; }
.guide-fig-side { width: 360px; height: 360px; }
.guide-callout { position: absolute; font-size: 15px; line-height: 1.2; color: rgb(11,11,11); }
.guide-note { font-size: 16px; color: rgb(11,11,11); margin-top: 6px; }
.guide-buttons { display: flex; justify-content: flex-end; align-items: center; margin-top: 18px; }
.btn { height: 58px; border-radius: 14px; font-size: 20px; display: flex; align-items: center; padding: 0 26px; }
.guide-back { background: rgb(240,239,236); color: rgb(11,11,11); margin-right: 14px; }
.guide-ready { background: rgb(42,120,214); color: #fff; font-size: 22px; font-weight: bold; padding: 0 40px; }
.wrap { display: inline-block; padding: 2px; }
.stack .sub { font-size: 20px; color: rgb(11,11,11); margin: 10px 0 26px; text-align: center; }
"""


def card(target):
    return f"""<div class="card">
  <div class="guide-title">Before you start</div>
  <div class="guide-sub">Take up this position when you step onto the green circles.</div>
  <div class="guide-row">
    <div class="guide-panel"><div class="card-label">SETUP</div>{front().html('guide-fig-front')}</div>
    <div class="guide-panel guide-panel-side"><div class="card-label">AT THE BOTTOM: {target.upper()}</div>
      {side(target).html('guide-fig-side')}<div class="guide-note">{DEPTH_CUE[target]}</div></div>
  </div>
  <div class="guide-buttons"><div class="btn guide-back">Back</div><div class="btn guide-ready">I'm ready</div></div>
</div>"""


def main(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    with sync_playwright() as pw:
        b = pw.chromium.launch(); p = b.new_page()
        for t in ("partial", "parallel", "deep"):
            p.set_content(f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS}</style></head>"
                          f"<body><div class='wrap'>{card(t)}</div></body></html>")
            box = p.locator(".wrap").bounding_box()
            w, h = math.ceil(box["width"]), math.ceil(box["height"])
            p.pdf(path=os.path.join(out_dir, f"setup_guide_{t}.pdf"), width=f"{w}px", height=f"{h}px",
                  print_background=True, margin={"top": "0", "right": "0", "bottom": "0", "left": "0"})
            p.set_viewport_size({"width": w, "height": h})
            p.screenshot(path=os.path.join(out_dir, f"setup_guide_{t}.png"), clip={"x": 0, "y": 0, "width": w, "height": h},
                         scale="device")
        body = (f"<div class='top'>{card('parallel')}</div><div class='sub'>(a) Parallel target</div>"
                f"<div class='pair'><div class='cell'><div class='zoom'>{card('partial')}</div>"
                f"<div class='sub'>(b) Partial target</div></div>"
                f"<div class='cell'><div class='zoom'>{card('deep')}</div>"
                f"<div class='sub'>(c) Deep target</div></div></div>")
        p.set_content(f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS}"
                      ".pair{display:flex;gap:24px}.cell{flex:1 1 0;min-width:0}</style></head>"
                      f"<body><div class='wrap stack'>{body}</div></body></html>")
        p.evaluate("""() => { const W = document.querySelector('.top .card').offsetWidth;
            const cell = (W - 24) / 2; document.querySelector('.pair').style.width = W + 'px';
            document.querySelectorAll('.zoom').forEach(z => { const c = z.firstElementChild;
              c.style.width = W + 'px'; z.style.zoom = cell / W; }); }""")
        box = p.locator(".wrap").bounding_box()
        p.pdf(path=os.path.join(out_dir, "setup_guide_all.pdf"), width=f"{math.ceil(box['width'])}px",
              height=f"{math.ceil(box['height'])}px", print_background=True,
              margin={"top": "0", "right": "0", "bottom": "0", "left": "0"})
        b.close()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "figures")
