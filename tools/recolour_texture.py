"""Recolour the clothing in an SMPL-X albedo texture."""
import argparse, os
import numpy as np
from PIL import Image
Image.MAX_IMAGE_PIXELS = None

SRC = "SMPLX-Unity/Assets/SMPLX/Textures/smplx_texture_{sex}_alb.png"
OUTDIR = "SMPLX-Unity/Assets/Avatars/Textures"
PREVDIR = "tools/_texture_previews"
OUT = OUTDIR + "/smplx_texture_{sex}_alb_custom.png"

GARMENTS = {
    ("f", "bottom"): dict(hue=(180, 235), sat=(0.12, 0.55), val=(0.08, 0.58), name="jeans"),
    ("f", "top"):    dict(hue=None,       sat=(0.00, 0.09), val=(0.55, 1.00), name="white tee"),
    ("m", "bottom"): dict(hue=(158, 192), sat=(0.03, 0.22), val=(0.18, 0.58), name="shorts"),
    ("m", "top"):    dict(hue=(6.5, 10.0), sat=(0.18, 0.34), val=(0.60, 0.80), name="salmon tee"),
}


def to_hsv(a):
    mx = a.max(axis=2); mn = a.min(axis=2)
    v = mx
    s = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0.0)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    d = mx - mn + 1e-6
    h = np.zeros_like(r)
    m = mx == r; h[m] = ((g - b)[m] / d[m]) % 6
    m = mx == g; h[m] = ((b - r)[m] / d[m]) + 2
    m = mx == b; h[m] = ((r - g)[m] / d[m]) + 4
    return (h * 60) % 360, s, v


def hex_rgb(t):
    t = t.lstrip("#")
    return np.array([int(t[i:i+2], 16) for i in (0, 2, 4)], float) / 255.0


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--sex", choices=["m", "f"], required=True)
    p.add_argument("--garment", choices=["top", "bottom"], required=True)
    p.add_argument("--color", required=True, help='target colour, e.g. "#1c1c20"')
    p.add_argument("--preview", action="store_true", help="also write a mask overlay")
    p.add_argument("--fresh", action="store_true", help="start from the stock texture")
    a = p.parse_args()

    os.makedirs(OUTDIR, exist_ok=True)
    os.makedirs(PREVDIR, exist_ok=True)
    out = OUT.format(sex=a.sex)
    src = SRC.format(sex=a.sex) if (a.fresh or not os.path.exists(out)) else out
    print(f"reading {src}")
    im = Image.open(src)
    alpha = im.getchannel("A") if im.mode == "RGBA" else None
    rgb = np.asarray(im.convert("RGB")).astype(np.float32) / 255.0

    spec = GARMENTS[(a.sex, a.garment)]
    h, s, v = to_hsv(rgb)
    m = (s >= spec["sat"][0]) & (s <= spec["sat"][1]) & \
        (v >= spec["val"][0]) & (v <= spec["val"][1])
    if spec["hue"] is not None:
        lo, hi = spec["hue"]
        m &= (h >= lo) & (h <= hi)
    pct = 100.0 * m.mean()
    print(f"garment '{spec['name']}': {m.sum():,} px selected ({pct:.2f}% of the texture)")
    if pct < 0.5:
        print("!! almost nothing selected — the window may not fit this texture.")
    if pct > 35:
        print("!! over a third of the texture selected — that is too much, check the preview.")

    tgt = hex_rgb(a.color)
    tv = tgt.max()
    if tv < 1e-3:
        tgt, tv = np.array([0.06, 0.06, 0.07]), 0.07
    ref = np.median(v[m]) if m.any() else 1.0
    scale = np.clip(v[m] / max(ref, 1e-6), 0.35, 1.9)
    rgb[m] = np.clip(tgt[None, :] * scale[:, None] * (tv / max(tv, 1e-6)), 0, 1)

    if a.preview:
        ov = (np.asarray(Image.open(src).convert("RGB")).astype(np.float32) / 255.0)
        ov[m] = 0.5 * ov[m] + 0.5 * np.array([1.0, 0.0, 1.0])
        Image.fromarray((ov * 255).astype(np.uint8)).resize((1024, 1024), Image.LANCZOS) \
            .save(f"{PREVDIR}/_mask_{a.sex}_{a.garment}.png")
        print(f"wrote {PREVDIR}/_mask_{a.sex}_{a.garment}.png (magenta = what will change)")

    res = Image.fromarray((rgb * 255).astype(np.uint8))
    if alpha is not None:
        res.putalpha(alpha)
    res.save(out, optimize=False, compress_level=6)
    print(f"wrote {out}  ({os.path.getsize(out)/1e6:.1f} MB)")


if __name__ == "__main__":
    main()
