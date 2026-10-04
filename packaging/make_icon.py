"""Draws the app icon (the 文A mark of the sidebar) as packaging/app.ico, all Windows sizes."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
FONTS = Path(r"C:\Windows\Fonts")


def _font(size: int, *names: str) -> ImageFont.FreeTypeFont:
    for name in names:
        if (FONTS / name).exists():
            return ImageFont.truetype(str(FONTS / name), size)
    return ImageFont.load_default(size)


def draw(size: int = 1024) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    # rounded square with a diagonal blue → teal gradient
    gradient = Image.new("RGBA", (size, size))
    px = gradient.load()
    top, bottom = (29, 111, 224), (20, 170, 190)
    for y in range(size):
        for x in range(size):
            t = (x + y) / (2 * size)
            px[x, y] = tuple(int(a + (b - a) * t) for a, b in zip(top, bottom, strict=True)) + (255,)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size - 1, size - 1), radius=size // 5, fill=255)
    img.paste(gradient, (0, 0), mask)
    d = ImageDraw.Draw(img)
    kanji = _font(int(size * 0.50), "meiryob.ttc", "YuGothB.ttc", "msgothic.ttc")
    latin = _font(int(size * 0.36), "segoeuib.ttf", "arialbd.ttf")
    d.text((size * 0.42, size * 0.47), "文", font=kanji, fill="white", anchor="mm")
    d.text((size * 0.74, size * 0.66), "A", font=latin, fill="white", anchor="mm")
    return img


def main() -> Path:
    target = HERE / "app.ico"
    draw().save(target, sizes=[(s, s) for s in (16, 20, 24, 32, 40, 48, 64, 128, 256)])
    return target


if __name__ == "__main__":
    print(main())
