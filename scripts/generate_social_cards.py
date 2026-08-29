from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "public" / "assets"
OUTPUT = ASSETS / "social"
ICON = ASSETS / "ask-crump-app-icon-v2-1024.png"
WORDMARK = ASSETS / "brand" / "crump-horizontal-light.png"

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


def portrait_background(width: int, height: int) -> Image.Image:
    image = Image.new("RGB", (width, height), (5, 6, 8))
    pixels = image.load()
    for y in range(height):
        for x in range(width):
            distance = ((x - width * 0.5) ** 2 + (y - height * 0.43) ** 2) ** 0.5
            glow = max(0.0, 1.0 - distance / (width * 0.78))
            lower_glow = max(0.0, 1.0 - abs(y - height * 0.83) / (height * 0.26))
            pixels[x, y] = (
                int(5 + 10 * glow + 9 * lower_glow),
                int(6 + 8 * glow + 6 * lower_glow),
                int(8 + 3 * glow),
            )
    return image


def render_portrait_card(filename: str, eyebrow: str, headline: str, detail: str) -> None:
    width, height = 1080, 1350
    image = portrait_background(width, height).convert("RGBA")

    ribbons = Image.new("RGBA", image.size, (0, 0, 0, 0))
    ribbon_draw = ImageDraw.Draw(ribbons)
    ribbon_draw.polygon(
        ((-130, 1160), (490, 1050), (1160, 1270), (1160, 1410), (420, 1160), (-130, 1330)),
        fill=(221, 192, 112, 26),
    )
    ribbon_draw.polygon(
        ((-70, 1280), (540, 1110), (1160, 1150), (1160, 1265), (520, 1205), (-70, 1390)),
        fill=(221, 192, 112, 18),
    )
    ribbons = ribbons.filter(ImageFilter.GaussianBlur(22))
    image = Image.alpha_composite(image, ribbons)

    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((34, 34, width - 34, height - 34), radius=28, outline=(221, 192, 112, 68), width=1)
    draw.line((78, 158, width - 78, 158), fill=(221, 192, 112, 70), width=1)
    draw.line((78, height - 136, width - 78, height - 136), fill=(221, 192, 112, 70), width=1)
    draw.line((-50, 1235, 505, 1095), fill=(221, 192, 112, 54), width=2)
    draw.line((505, 1095, 1130, 1220), fill=(221, 192, 112, 42), width=2)

    wordmark = Image.open(WORDMARK).convert("RGBA")
    wordmark.thumbnail((470, 124), Image.Resampling.LANCZOS)
    image.alpha_composite(wordmark, ((width - wordmark.width) // 2, 61))

    eyebrow_font = font(SANS_CANDIDATES, 20)
    headline_font = font(SERIF_CANDIDATES, 76)
    detail_font = font(SANS_CANDIDATES, 25)
    sequence_font = font(SANS_CANDIDATES, 15)
    footer_font = font(SANS_CANDIDATES, 16)

    eyebrow_box = draw.textbbox((0, 0), eyebrow.upper(), font=eyebrow_font)
    draw.text(((width - (eyebrow_box[2] - eyebrow_box[0])) / 2, 255), eyebrow.upper(), font=eyebrow_font, fill=GOLD)

    headline_lines = wrap_text(draw, headline, headline_font, 850)
    headline_line_height = 88
    headline_y = 328
    for line in headline_lines:
        box = draw.textbbox((0, 0), line, font=headline_font)
        draw.text(((width - (box[2] - box[0])) / 2, headline_y), line, font=headline_font, fill=OFF_WHITE)
        headline_y += headline_line_height

    detail_lines = wrap_text(draw, detail, detail_font, 790)
    detail_y = headline_y + 35
    for line in detail_lines:
        box = draw.textbbox((0, 0), line, font=detail_font)
        draw.text(((width - (box[2] - box[0])) / 2, detail_y), line, font=detail_font, fill=MUTED)
        detail_y += 39

    sequence = "THINK  ·  RESEARCH  ·  CREATE  ·  KEEP GOING"
    sequence_box = draw.textbbox((0, 0), sequence, font=sequence_font)
    draw.text(((width - (sequence_box[2] - sequence_box[0])) / 2, height - 189), sequence, font=sequence_font, fill=(193, 163, 88))
    draw.text((78, height - 103), "A CLEVER CRUMP COMPANY", font=footer_font, fill=(195, 188, 167))
    domain = "ASKCRUMP.COM"
    domain_box = draw.textbbox((0, 0), domain, font=footer_font)
    draw.text((width - 78 - (domain_box[2] - domain_box[0]), height - 103), domain, font=footer_font, fill=GOLD)

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

    portrait_cards = (
        (
            "ask-crump-workspace-portrait.png",
            "An AI workspace",
            "Work that continues.",
            "Conversations, Projects, research, files, and finished work—together in one place.",
        ),
        (
            "ask-crump-presentations-portrait.png",
            "AI presentation maker",
            "From an idea to an editable PowerPoint.",
            "Build a structured .pptx draft, download it, revise it, and keep the work moving.",
        ),
    )
    for card in portrait_cards:
        render_portrait_card(*card)

if __name__ == "__main__":
    main()
