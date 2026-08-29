from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
WORDMARK = ROOT / "public" / "assets" / "brand" / "crump-horizontal-light.png"
TAGLINE = "AN AI WORKSPACE FOR WORK THAT CONTINUES"
TAGLINE_TOP = 238
TAGLINE_X = 270
TAGLINE_WIDTH = 900
TAGLINE_Y = 246
TAGLINE_COLOR = (205, 175, 98, 255)


def load_font(size: int) -> ImageFont.FreeTypeFont:
    candidates = (
        Path("C:/Windows/Fonts/bahnschrift.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    )
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default(size=size)


def draw_tracked_text(
    draw: ImageDraw.ImageDraw,
    position: tuple[int, int],
    text: str,
    font: ImageFont.FreeTypeFont,
    target_width: int,
    fill: tuple[int, int, int, int],
) -> None:
    glyph_widths = [draw.textlength(character, font=font) for character in text]
    base_width = sum(glyph_widths)
    tracking = max(0.0, (target_width - base_width) / max(1, len(text) - 1))
    x, y = position
    for character, glyph_width in zip(text, glyph_widths):
        draw.text((x, y), character, font=font, fill=fill)
        x += glyph_width + tracking


def main() -> None:
    image = Image.open(WORDMARK).convert("RGBA")
    if image.size != (1200, 296):
        raise ValueError(f"Expected a 1200x296 wordmark, got {image.size!r}")

    # Preserve the approved mark, ASK CRUMP lettering, and rule exactly. Only the
    # legacy descriptor beneath the rule is replaced with the current positioning.
    image.paste((0, 0, 0, 0), (0, TAGLINE_TOP, image.width, image.height))
    draw = ImageDraw.Draw(image)
    draw_tracked_text(
        draw,
        (TAGLINE_X, TAGLINE_Y),
        TAGLINE,
        load_font(18),
        TAGLINE_WIDTH,
        TAGLINE_COLOR,
    )

    temporary = WORDMARK.with_suffix(".tmp.png")
    image.save(temporary, format="PNG", optimize=True)
    temporary.replace(WORDMARK)


if __name__ == "__main__":
    main()
