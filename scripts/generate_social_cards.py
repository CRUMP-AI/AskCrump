from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "public" / "assets"
OUTPUT = ASSETS / "social"
ICON = ASSETS / "ask-crump-app-icon-v2-1024.png"

WIDTH = 1200
HEIGHT = 630
GOLD = (221, 192, 112)
OFF_WHITE = (245, 242, 233)
MUTED = (170, 170, 166)


def font(candidates: tuple[str, ...], size: int) -> ImageFont.FreeTypeFont:
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default(size=size)


SERIF_CANDIDATES = (
    "C:/Windows/Fonts/BASKVILL.TTF",
    "C:/Windows/Fonts/georgia.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
)
SANS_CANDIDATES = (
    "C:/Windows/Fonts/bahnschrift.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)


def gradient_background() -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), (6, 8, 11))
    pixels = image.load()
    for y in range(HEIGHT):
        for x in range(WIDTH):
            distance = ((x - 250) ** 2 + (y - 315) ** 2) ** 0.5
            glow = max(0.0, 1.0 - distance / 640.0)
            edge = x / WIDTH
            pixels[x, y] = (
                int(6 + 15 * glow + 3 * edge),
                int(8 + 12 * glow + 3 * edge),
                int(11 + 5 * glow),
            )
    return image


def wrap_text(draw: ImageDraw.ImageDraw, text: str, typeface: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if draw.textbbox((0, 0), candidate, font=typeface)[2] <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def render_card(filename: str, eyebrow: str, headline: str, detail: str) -> None:
    image = gradient_background()

    halo = Image.new("RGBA", image.size, (0, 0, 0, 0))
    halo_draw = ImageDraw.Draw(halo)
    halo_draw.ellipse((25, 90, 460, 525), fill=(221, 192, 112, 42))
    halo = halo.filter(ImageFilter.GaussianBlur(80))
    image = Image.alpha_composite(image.convert("RGBA"), halo)

    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((28, 28, WIDTH - 28, HEIGHT - 28), radius=24, outline=(221, 192, 112, 64), width=1)
    draw.line((545, 118, WIDTH - 84, 118), fill=(221, 192, 112, 90), width=1)

    icon = Image.open(ICON).convert("RGB").resize((214, 214), Image.Resampling.LANCZOS)
    icon_mask = Image.new("L", icon.size, 0)
    ImageDraw.Draw(icon_mask).rounded_rectangle((0, 0, 213, 213), radius=44, fill=255)
    image.paste(icon, (116, 194), icon_mask)

    brand_font = font(SANS_CANDIDATES, 28)
    eyebrow_font = font(SANS_CANDIDATES, 20)
    headline_font = font(SERIF_CANDIDATES, 64)
    detail_font = font(SANS_CANDIDATES, 25)
    footer_font = font(SANS_CANDIDATES, 17)

    draw.text((84, 76), "ASK CRUMP", font=brand_font, fill=GOLD)
    draw.text((545, 76), eyebrow.upper(), font=eyebrow_font, fill=(184, 156, 86))

    y = 164
    for line in wrap_text(draw, headline, headline_font, 565):
        draw.text((545, y), line, font=headline_font, fill=OFF_WHITE)
        y += 72

    y += 17
    for line in wrap_text(draw, detail, detail_font, 540):
        draw.text((545, y), line, font=detail_font, fill=MUTED)
        y += 36

    draw.text((84, HEIGHT - 82), "AN AI WORKSPACE FOR WORK THAT CONTINUES", font=footer_font, fill=(157, 137, 85))
    draw.text((WIDTH - 270, HEIGHT - 82), "ASKCRUMP.COM", font=footer_font, fill=(157, 137, 85))

    OUTPUT.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(OUTPUT / filename, format="PNG", optimize=True)


def main() -> None:
    cards = (
        (
            "ask-crump-workspace.png",
            "Private · Persistent · Built for output",
            "Work that continues.",
            "Keep conversations, Projects, files, and finished work together—and come back when the work moves again.",
        ),
        (
            "ask-crump-presentations.png",
            "AI presentation maker",
            "From an idea to an editable PowerPoint.",
            "Build a structured .pptx draft, download it, revise it, and keep the work moving inside one workspace.",
        ),
        (
            "ask-crump-documents.png",
            "AI document generator",
            "Turn source material into a real document.",
            "Create editable Word and PDF drafts with structure, evidence, and a clear path to the next revision.",
        ),
        (
            "ask-crump-resumes.png",
            "AI resume builder",
            "Turn real experience into an editable resume.",
            "Shape accurate experience for a target role, download the Word draft, revise it, and keep the work moving.",
        ),
        (
            "ask-crump-video.png",
            "AI video generator",
            "Direct one clear scene at a time.",
            "Choose a purpose-built video mode, see the credit cost, generate the shot, and keep the result in your workspace.",
        ),
    )
    for card in cards:
        render_card(*card)


if __name__ == "__main__":
    main()
