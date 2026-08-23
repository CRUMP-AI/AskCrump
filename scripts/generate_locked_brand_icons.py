"""Derive every install icon from the locked Ask Crump app mark.

This is intentionally deterministic. It must never redraw, reinterpret, or
substitute the product mark. A checksum guard makes an intentional brand-source
change necessary before release assets can change.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'public' / 'assets' / 'icon-1024.png'
LOCKED_SHA256 = 'f7526459bee2624d39b1ebc8a668596bb36c447217c1f730afa7ab63db649301'
PUBLIC_SIZES = (180, 192, 512, 1024)
SPLASH_SIZE = 2732
SPLASH_MARK_SIZE = 1180


def main() -> None:
    payload = SOURCE.read_bytes()
    actual = sha256(payload).hexdigest()
    if actual != LOCKED_SHA256:
        raise SystemExit(
            'The locked Ask Crump icon source changed. Review the brand update and '
            'update LOCKED_SHA256 intentionally before regenerating release assets.'
        )
    with Image.open(SOURCE) as source:
        master = source.convert('RGB')
        if master.size != (1024, 1024):
            raise SystemExit(f'Locked icon must be 1024×1024; found {master.size}.')
        for size in PUBLIC_SIZES:
            output = ROOT / 'public' / 'assets' / f'ask-crump-app-icon-v2-{size}.png'
            master.resize((size, size), Image.Resampling.LANCZOS).save(
                output,
                format='PNG',
                optimize=True,
            )
        # Capacitor's native asset generator consumes this exact source.
        master.save(ROOT / 'resources' / 'icon.png', format='PNG', optimize=True)
        # Keep the native launch identity on the same locked source. The canvas
        # color is sampled from the master so the centered square has no seam.
        splash = Image.new('RGB', (SPLASH_SIZE, SPLASH_SIZE), master.getpixel((0, 0)))
        splash_mark = master.resize((SPLASH_MARK_SIZE, SPLASH_MARK_SIZE), Image.Resampling.LANCZOS)
        inset = (SPLASH_SIZE - SPLASH_MARK_SIZE) // 2
        splash.paste(splash_mark, (inset, inset))
        splash.save(ROOT / 'resources' / 'splash.png', format='PNG', optimize=True)


if __name__ == '__main__':
    main()
