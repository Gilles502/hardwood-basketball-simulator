"""Render the Hardwood app icon (a ball whose seams draw an H) to assets/hardwood.ico.

The same drawing lives as SVG in frontend/public/favicon.svg and frontend/src/components/HardwoodLogo.tsx;
keep the three in step. The .ico is committed, so the exe build does not need this script.
Run: python scripts/make_icon.py   (needs Pillow)
"""
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "hardwood.ico"
SIZES = [16, 20, 24, 32, 40, 48, 64, 128, 256]

WOOD = (20, 16, 13, 255)  # #14100d
EMBER = (255, 106, 26, 255)  # #ff6a1a
SS = 16  # supersampling: the 64-unit drawing is rendered at 1024 px, then scaled down


def _cubic(p0, p1, p2, p3, steps=200):
    pts = []
    for i in range(steps + 1):
        t = i / steps
        u = 1 - t
        x = u ** 3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t ** 3 * p3[0]
        y = u ** 3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t ** 3 * p3[1]
        pts.append((x * SS, y * SS))
    return pts


def render() -> Image.Image:
    size = 64 * SS
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=14 * SS, fill=WOOD)
    ball = (10 * SS, 10 * SS, 54 * SS, 54 * SS)  # center 32,32, radius 22
    draw.ellipse(ball, fill=EMBER)

    seams = Image.new("L", (size, size), 0)
    sd = ImageDraw.Draw(seams)
    r = 1.7 * SS  # stroke width 3.4, drawn as round stamps along each path (clean edges, round caps)
    for line in (
        _cubic((21, 9), (28, 22), (28, 42), (21, 55), steps=800),
        _cubic((43, 9), (36, 22), (36, 42), (43, 55), steps=800),
        [((8 + 48 * i / 800) * SS, 32 * SS) for i in range(801)],
    ):
        for x, y in line:
            sd.ellipse((x - r, y - r, x + r, y + r), fill=255)
    ball_mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(ball_mask).ellipse(ball, fill=255)
    img.paste(WOOD, (0, 0), ImageChops.multiply(seams, ball_mask))
    return img


def main() -> None:
    big = render()
    frames = [big.resize((s, s), Image.LANCZOS) for s in SIZES]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    frames[-1].save(OUT, format="ICO", sizes=[(s, s) for s in SIZES], append_images=frames[:-1])
    print(f"wrote {OUT.relative_to(ROOT)} ({', '.join(map(str, SIZES))} px)")


if __name__ == "__main__":
    main()
