"""Brand invariant regression: the production magnifying-glass logo and
favicon stay byte-identical, and the Apple UI Concept v2 prototype's
two-dot placeholder mark never ships.

Greg's hard rule (2026-11-08, restated for the v2 baseline 2026-11-11):
do not touch the logo. The concept prototype's glowing two-dot mark and
two-dot favicon are placeholders only and are explicitly excluded from
the approved direction.

The pinned hashes below are the exact bytes on main 6312b7ac, the v2
baseline. Any redraw, recolor, reinterpretation, or replacement of a
listed asset fails this file. The one pre-existing drift is recorded,
not hidden: BRAND_ASSET_HASHES.json lists a display hash for
crump-horizontal-light.png (8b586f63...) that matches neither the
brand/ nor the ask-crump-* file on disk; this file pins the actual
on-disk bytes (32831f47...) as the lock and does not re-litigate the
stale JSON entry.
"""

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
BRAND = PUBLIC / "assets" / "brand"

# Exact bytes on the v2 baseline (main 6312b7ac). Do not "refresh" these
# to make a change pass: a mismatch means a brand asset changed, and
# only Greg's explicit direction authorizes that.
PINNED_ASSETS = {
    # Favicon + install icons served by app.html and manifest.json.
    "assets/ask-crump-app-icon-v2-192.png":
        "39dd240fdd102bde9d946f49f8de7d0843f94f655a2ba904b786fa13f16fc643",
    "assets/ask-crump-app-icon-v2-180.png":
        "5ff6936e313afdf90fd4a2a3a050a67e44fb27c731aa405442c1ceff67635863",
    "assets/ask-crump-app-icon-v2-512.png":
        "62b709b8891a8121db8540cda59895dc6d6ac0edbbd729495b4d271b548bffc8",
    "assets/ask-crump-app-icon-v2-1024.png":
        "e58bc52d69cab6193bb3903f042313f01bf68e3413cc421f044f9b9f4488d960",
    "assets/icon-192.png":
        "011d58cba3392d5a0a0bea18ad9bbdbda91d6ca5327f0dbdd47a6f7b4e512124",
    "assets/icon-512.png":
        "4d32fadeb014909f0a69d405353e4caa931f4e3b155b83b79ff32c16d95a72c0",
    "assets/icon-1024.png":
        "f7526459bee2624d39b1ebc8a668596bb36c447217c1f730afa7ab63db649301",
    # Brand images referenced by the app shell and auth screens.
    "assets/brand/crump-mark-320.webp":
        "97a95059ad0997ffb88a78d6b3dca655eaf6efbd7945fcd60eacc7d494649917",
    "assets/brand/crump-shell-lockup-light.webp":
        "1e0438d65f43cc6f518995f526c7c1f47862f119aedb69a6cdffaf0cfee999df",
    "assets/brand/crump-mark.webp":
        "215795869583f9852802f4655f6bd2cfd434d7526c378dae721445a04728b60e",
    "assets/brand/crump-shell-lockup-light.png":
        "dbb9ec2f995a5074e3aa4e74174cdf8b8562c490714be3b5af65713472cf9d88",
    "assets/ask-crump-logo.png":
        "cf1e2df20a887ffc0d058211b7e266ce2dc2a94c7b322ef73e0ed02e8e48390e",
    "assets/logo-c.png":
        "2b84dc04adf7cb4b4624d54fbff9543c6e32ffd3dd2b9a9b85c97a8e6978d171",
    # Brand masters and display renders named by BRAND_ASSET_HASHES.json.
    "assets/brand/crump-mark-master.png":
        "5ba1f8de8b98e0ea693eddc6899beb761aec5bc51cb4467cdba5bcefc943cc6c",
    "assets/brand/crump-horizontal-light-master.png":
        "622085761c8f4ccf56cd93665d3e2908713e42bfa53b2091eaee9e34fb2f4219",
    "assets/brand/crump-horizontal-dark-master.png":
        "f2cfa6e00186ca1f3b35f25d6e1dc6746c621ec97f039fae9d615c56c38de110",
    "assets/brand/crump-wordmark-light-master.png":
        "b6497ca4b0120b69892c6d296f3093a14746469338c70da5990f9b15f4038982",
    "assets/brand/crump-wordmark-dark-master.png":
        "b7cd0a5d4a8a4ce40a4fa6ce14c23ef476406bed89240a8f3de466bdae3fc90a",
    "assets/brand/crump-mark.png":
        "4e71d1fe0f9d50ed3405b3fb1c248cb83377ec28ebce072c42c9ad4637cc4705",
    "assets/brand/crump-horizontal-light.png":
        "32831f47a67416d9864d17c0788d354382a829ab1092c7317c6ed70674541f71",
    "assets/brand/crump-horizontal-dark.png":
        "cbe5e67dbc3dd1d08870329ce21df6acbc30da7961a051703acf823553c9d2f6",
    "assets/brand/crump-wordmark-light.png":
        "cf4fc78edc21584bd1e2848a6fcc2f0a0cae9611364d5d375a1219131b4937ba",
    "assets/brand/crump-wordmark-dark.png":
        "7ccb2c64af3457b01d9872d5a365758b7dba1bb0cded51cb0aba3611e27a09e1",
}

# The prototype placeholder mark, in every form it could ship as. The
# scan below reads shipped files only (public/), never this test file.
FORBIDDEN_MARKERS = (
    "crump-pulse",
    "crump_pulse",
    "two-dot",
    "two_dot",
)

SCAN_SUFFIXES = {".css", ".js", ".mjs", ".cjs", ".html", ".json", ".ts"}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_production_brand_assets_are_byte_identical():
    for relative, expected in PINNED_ASSETS.items():
        path = PUBLIC / relative
        assert path.is_file(), f"missing brand asset: {relative}"
        assert _sha256(path) == expected, f"brand asset changed: {relative}"


def test_brand_asset_hash_lock_still_matches_its_masters():
    lock = json.loads((ROOT / "BRAND_ASSET_HASHES.json").read_text(encoding="utf-8"))
    for name, meta in lock["masters"].items():
        path = BRAND / name
        assert path.is_file(), f"missing brand master: {name}"
        assert _sha256(path) == meta["sha256"], f"brand master changed: {name}"
    # Display renders that matched the lock at the baseline keep matching.
    # (crump-horizontal-light.png is the one recorded pre-existing drift;
    # its bytes are pinned by test_production_brand_assets_are_byte_identical.)
    for name, meta in lock["display"].items():
        if name == "crump-horizontal-light.png":
            continue
        path = BRAND / name
        assert path.is_file(), f"missing brand display asset: {name}"
        assert _sha256(path) == meta["sha256"], f"brand display asset changed: {name}"


def test_favicon_and_touch_icons_stay_on_the_production_pngs():
    app = (PUBLIC / "app.html").read_text(encoding="utf-8")
    assert '<link rel="icon" type="image/png" href="/assets/ask-crump-app-icon-v2-192.png">' in app
    assert 'href="/assets/ask-crump-app-icon-v2-180.png"' in app
    assert "data:image/svg+xml" not in app
    manifest = json.loads((PUBLIC / "manifest.json").read_text(encoding="utf-8"))
    assert [icon["src"] for icon in manifest["icons"]] == [
        "/assets/ask-crump-app-icon-v2-192.png",
        "/assets/ask-crump-app-icon-v2-512.png",
        "/assets/ask-crump-app-icon-v2-1024.png",
    ]


def test_logo_references_keep_the_production_assets_and_names():
    app = (PUBLIC / "app.html").read_text(encoding="utf-8")
    # The shell lockup and the mark stay referenced with their production
    # paths, dimensions, and accessible names.
    assert "/assets/brand/crump-shell-lockup-light.webp" in app
    assert "/assets/brand/crump-mark-320.webp" in app
    assert 'alt="Ask Crump"' in app
    shell = (PUBLIC / "crump-vision-shell-1.0.js").read_text(encoding="utf-8")
    assert "/assets/brand/crump-mark-320.webp" in shell


def test_prototype_two_dot_mark_cannot_ship():
    hits = []
    for path in sorted(PUBLIC.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SCAN_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for marker in FORBIDDEN_MARKERS:
            if marker in text:
                hits.append(f"{path.relative_to(ROOT)}: {marker}")
    assert not hits, "prototype placeholder mark found in shipped files: " + "; ".join(hits)


def test_no_data_uri_favicon_in_shipped_pages():
    for path in sorted(PUBLIC.glob("*.html")):
        text = path.read_text(encoding="utf-8")
        assert "data:image/svg+xml" not in text, f"data-URI favicon in {path.name}"
