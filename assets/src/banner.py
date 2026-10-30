#!/usr/bin/env python3
"""Compose a 1200x480 Agent Kaizen banner from text-free artwork (Pillow)."""
import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


def compose(art: Path, out: Path, title_side: str) -> None:
    scale = 2
    width, height = 1200 * scale, 480 * scale
    with Image.open(art) as source:
        canvas = ImageOps.fit(source.convert("RGB"), (width, height),
                              method=Image.Resampling.LANCZOS).convert("RGBA")
    scrim = Image.new("RGBA", canvas.size)
    draw = ImageDraw.Draw(scrim)
    for x in range(width):
        if title_side == "left":
            strength = max(0.0, 1.0 - x / (width * 0.62))
        else:
            strength = max(0.0, 1.0 - abs(x - width / 2) / (width * 0.48))
        draw.line((x, 0, x, height), fill=(7, 16, 29, int(150 * strength)))
    canvas = Image.alpha_composite(canvas, scrim)
    draw = ImageDraw.Draw(canvas)
    fonts = Path("/System/Library/Fonts")
    title = ImageFont.truetype(str(fonts / "Avenir Next.ttc"), 64 * scale)
    subtitle = ImageFont.truetype(str(fonts / "Avenir Next.ttc"), 21 * scale)
    japanese = ImageFont.truetype(str(fonts / "Hiragino Sans GB.ttc"), 25 * scale)
    anchor = "la" if title_side == "left" else "ma"
    x = 60 * scale if title_side == "left" else width // 2
    draw.text((x, 126 * scale), "改善", font=japanese, fill="#6ee7d2", anchor=anchor)
    draw.text((x, 169 * scale), "Agent Kaizen", font=title, fill="#f8fbff", anchor=anchor)
    draw.text((x, 260 * scale), "continuous improvement for AI coding agents",
              font=subtitle, fill="#d6e4ef", anchor=anchor)
    canvas = canvas.convert("RGB").resize((1200, 480), Image.Resampling.LANCZOS)
    # Opaque, subtle keyline keeps the edge visible on both GitHub themes.
    ImageDraw.Draw(canvas).rectangle((0, 0, 1199, 479), outline="#526272", width=1)
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out, format="PNG")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--art", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--title-side", choices=("left", "center"), default="left")
    args = parser.parse_args()
    compose(args.art, args.out, args.title_side)


if __name__ == "__main__":
    main()
