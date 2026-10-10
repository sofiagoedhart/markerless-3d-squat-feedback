"""Generate an exact-scale printable calibration board as a PDF."""
import argparse
import os

from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

PAPERS_MM = {
    "A0": (1189, 841), "A1": (841, 594), "A2": (594, 420),
    "A3": (420, 297), "A4": (297, 210),
}


def build(cols_sq, rows_sq, square_mm, paper, out):
    pw, ph = PAPERS_MM[paper]
    bw, bh = cols_sq * square_mm, rows_sq * square_mm
    quiet = square_mm * 0.6
    need_w, need_h = bw + 2 * quiet, bh + 2 * quiet
    if need_w > pw or need_h > ph:
        raise SystemExit(
            f"Board {bw:.0f}x{bh:.0f} mm + {quiet:.0f} mm border needs "
            f"{need_w:.0f}x{need_h:.0f} mm but {paper} is {pw}x{ph} mm.\n"
            f"Largest square that fits {paper}: "
            f"{min(pw/(cols_sq+1.2), ph/(rows_sq+1.2)):.1f} mm")

    c = canvas.Canvas(out, pagesize=(pw * mm, ph * mm))
    x0, y0 = (pw - bw) / 2.0, (ph - bh) / 2.0
    c.setFillColorRGB(0, 0, 0); c.setStrokeColorRGB(0, 0, 0)
    for r in range(rows_sq):
        for col in range(cols_sq):
            if (r + col) % 2 == 0:
                c.rect((x0 + col * square_mm) * mm, (y0 + r * square_mm) * mm,
                       square_mm * mm, square_mm * mm, stroke=0, fill=1)

    inner_c, inner_r = cols_sq - 1, rows_sq - 1
    c.setFont("Helvetica", 9)
    c.drawString(12 * mm, 8 * mm,
                 f"{cols_sq}x{rows_sq} squares @ {square_mm:.1f} mm  ->  "
                 f"CHECKERBOARD = ({inner_c}, {inner_r}) inner corners   |   "
                 f"PRINT AT 100% / ACTUAL SIZE - do not 'fit to page'")
    c.drawString(12 * mm, (ph - 10) * mm,
                 f"scale check: the bar below is exactly {int(bw)} mm "
                 f"(= the {inner_c}-inner-corner span)")
    c.setLineWidth(0.6)
    c.line(x0 * mm, (ph - 14) * mm, (x0 + bw) * mm, (ph - 14) * mm)
    for xx in (x0, x0 + bw):
        c.line(xx * mm, (ph - 17) * mm, xx * mm, (ph - 11) * mm)
    c.showPage(); c.save()

    print(f"wrote {out}")
    print(f"  paper        : {paper} landscape ({pw} x {ph} mm)")
    print(f"  squares      : {cols_sq} x {rows_sq} @ {square_mm:.1f} mm "
          f"-> pattern {bw:.0f} x {bh:.0f} mm")
    print(f"  INNER CORNERS: ({inner_c}, {inner_r})   <- set CHECKERBOARD to this")
    print(f"  parity       : {'ODD x EVEN - no 180 deg ambiguity. Good.' if (inner_c % 2) != (inner_r % 2) else '!! same parity - 180 deg ambiguity remains'}")
    print(f"  at 4 m with fx~1400 this is ~{1400*square_mm/4000:.0f} px per square")
    print("  AFTER PRINTING: steel-rule the long span, then set SQUARE_W_MM/"
          "SQUARE_H_MM from that measurement.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cols", type=int, default=10, help="squares across")
    ap.add_argument("--rows", type=int, default=7, help="squares down")
    ap.add_argument("--square", type=float, default=80.0, help="square size in mm")
    ap.add_argument("--paper", default="A1", choices=list(PAPERS_MM))
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    out = a.out or f"calib/chessboard_{a.cols}x{a.rows}_{a.square:.0f}mm_{a.paper}.pdf"
    os.makedirs(os.path.dirname(out), exist_ok=True)
    build(a.cols, a.rows, a.square, a.paper, out)
