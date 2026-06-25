"""Generate the add-in button icons into resources/ (16/32/64 px PNGs).
Run once: `python generate_icon.py`. Motif: a force arrow driven into a
workpiece = cutting force. Drawn at high res and downsampled for crisp edges.
"""
from PIL import Image, ImageDraw

S = 256
ORANGE = (226, 120, 38, 255)
STEEL = (96, 118, 150, 255)
CHIP = (240, 176, 90, 255)


def draw(s):
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    bar_top = s * 0.66
    # workpiece
    d.rounded_rectangle([s * 0.10, bar_top, s * 0.90, s * 0.86],
                        radius=s * 0.05, fill=STEEL)
    # force arrow (shaft + head) pointing down into the workpiece
    ax = s * 0.5
    sw = s * 0.14
    d.rectangle([ax - sw / 2, s * 0.12, ax + sw / 2, bar_top - s * 0.10], fill=ORANGE)
    d.polygon([(ax - s * 0.17, bar_top - s * 0.14),
               (ax + s * 0.17, bar_top - s * 0.14),
               (ax, bar_top + s * 0.03)], fill=ORANGE)
    # chips flying off the impact point
    r = s * 0.035
    for cx, cy in [(0.30, 0.60), (0.70, 0.62), (0.24, 0.70), (0.77, 0.71)]:
        d.ellipse([s * cx - r, s * cy - r, s * cx + r, s * cy + r], fill=CHIP)
    return img


if __name__ == "__main__":
    import os
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources")
    os.makedirs(out, exist_ok=True)
    master = draw(S)
    for size in (16, 32, 64):
        master.resize((size, size), Image.LANCZOS).save(
            os.path.join(out, f"{size}x{size}.png"))
    print("icons written to", out)
