"""make_mannequin_texture.py — build a FEATURELESS clothed avatar texture."""
import argparse, os
import numpy as np
from PIL import Image
Image.MAX_IMAGE_PIXELS = None

SRC_ALB = "SMPLX-Unity/Assets/SMPLX/Textures/smplx_texture_{sex}_alb.png"
SRC_NRM = "SMPLX-Unity/Assets/SMPLX/Textures/smplx_texture_{sex}_nrm.png"
OUTDIR  = "SMPLX-Unity/Assets/Avatars/Textures"
OUT_ALB = OUTDIR + "/mannequin_{sex}_alb.png"
OUT_NRM = OUTDIR + "/mannequin_{sex}_nrm.png"

GARMENTS = {
    ("f", "bottom"): dict(hue=(180, 235), sat=(0.12, 0.55), val=(0.08, 0.58)),
    ("f", "top"):    dict(hue=None,       sat=(0.00, 0.09), val=(0.55, 1.00)),
    ("m", "bottom"): dict(hue=(158, 192), sat=(0.03, 0.22), val=(0.18, 0.58)),
    ("m", "top"):    dict(hue=(6.5, 10.0), sat=(0.18, 0.34), val=(0.60, 0.80)),
}
HEAD_UV = (0.00, 0.66, 0.00, 0.48)
EYE_UV  = (0.53, 0.63, 0.38, 0.48)


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


def hexc(t):
    t = t.lstrip("#")
    return np.array([int(t[i:i+2], 16) for i in (0, 2, 4)], float) / 255.0


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--sex", choices=["m", "f"], required=True)
    p.add_argument("--skin", default="#c9a68c")
    p.add_argument("--top", default="#26262b")
    p.add_argument("--bottom", default="#141417")
    p.add_argument("--shading", type=float, default=0.35,
                   help="0 = perfectly flat skin, 1 = keep the original shading")
    a = p.parse_args()
    os.makedirs(OUTDIR, exist_ok=True)

    src = SRC_ALB.format(sex=a.sex)
    im = Image.open(src)
    alpha = im.getchannel("A") if im.mode == "RGBA" else None
    rgb = np.asarray(im.convert("RGB")).astype(np.float32) / 255.0
    H, W, _ = rgb.shape
    h, s, v = to_hsv(rgb)

    masks = {}
    for part in ("top", "bottom"):
        w = GARMENTS[(a.sex, part)]
        m = (s >= w["sat"][0]) & (s <= w["sat"][1]) & (v >= w["val"][0]) & (v <= w["val"][1])
        if w["hue"] is not None:
            m &= (h >= w["hue"][0]) & (h <= w["hue"][1])
        masks[part] = m
        print(f"  {part:6} garment: {m.sum():,} px ({100*m.mean():.1f}%)")
    cloth = masks["top"] | masks["bottom"]
    eye = np.zeros((H, W), bool)
    ex0, ex1, ey0, ey1 = EYE_UV
    eye[int(ey0*H):int(ey1*H), int(ex0*W):int(ex1*W)] = True
    n_eye = int((cloth & eye).sum())
    cloth &= ~eye
    if n_eye:
        print(f"  eyeball island rescued from the garment mask: {n_eye:,} px")
    print(f"  skin (everything else): {(~cloth).sum():,} px ({100*(~cloth).mean():.1f}%)")

    out = np.zeros_like(rgb)

    skin = hexc(a.skin)
    body_v = v[~cloth]
    ref = np.median(body_v) if body_v.size else 1.0
    head = np.zeros((H, W), bool)
    x0, x1, y0, y1 = HEAD_UV
    head[int(y0*H):int(y1*H), int(x0*W):int(x1*W)] = True
    flat = (~cloth) & (head | eye)
    soft = (~cloth) & (~head) & (~eye)
    out[flat] = skin
    if a.shading <= 0.001:
        out[soft] = skin
    else:
        sc = np.clip(v[soft] / max(ref, 1e-6), 0.55, 1.5)
        sc = 1.0 + (sc - 1.0) * float(a.shading)
        out[soft] = np.clip(skin[None, :] * sc[:, None], 0, 1)
    print(f"  head region forced perfectly flat: {flat.sum():,} px")

    for part, col in (("top", a.top), ("bottom", a.bottom)):
        m = masks[part]
        if not m.any():
            continue
        tgt = hexc(col); tv = max(tgt.max(), 1e-6)
        if tv < 0.02:
            tgt, tv = np.array([0.06, 0.06, 0.07]), 0.07
        r2 = np.median(v[m])
        sc = np.clip(v[m] / max(r2, 1e-6), 0.35, 1.9)
        out[m] = np.clip(tgt[None, :] * sc[:, None], 0, 1)

    res = Image.fromarray((out * 255).astype(np.uint8))
    if alpha is not None:
        res.putalpha(alpha)
    oa = OUT_ALB.format(sex=a.sex)
    res.save(oa, compress_level=6)
    print(f"  wrote {oa}  ({os.path.getsize(oa)/1e6:.1f} MB)")

    snrm = SRC_NRM.format(sex=a.sex)
    if os.path.exists(snrm):
        nm = Image.open(snrm).convert("RGB")
        n = np.asarray(nm).copy()
        x0, x1, y0, y1 = HEAD_UV
        n[int(y0*H):int(y1*H), int(x0*W):int(x1*W)] = (128, 128, 255)
        on = OUT_NRM.format(sex=a.sex)
        Image.fromarray(n).save(on, compress_level=6)
        print(f"  wrote {on}  (head region flattened to neutral)")


if __name__ == "__main__":
    main()
