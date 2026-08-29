from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_v1_header_brand_is_not_replaced_by_legacy_shells():
    legacy_43 = read("public/crump-4.3.js")
    legacy_50 = read("public/crump-5.0.js")

    assert "if (document.body.classList.contains('crump-v1-body')) return;" in legacy_43
    assert "!document.body.classList.contains('crump-v1-body')" in legacy_50


def test_v1_brand_guard_reuses_the_initial_header_image():
    body = read("public/crump-v1-body.js")

    assert "const existing = host.querySelector(':scope > img');" in body
    assert "existing.classList.add('v1-header-logo', 'v1-body-header-logo');" in body
    assert "existing.loading = 'eager';" in body
    assert "existing.decoding = 'sync';" in body
    assert "existing.fetchPriority = 'high';" in body


def test_workspace_positioning_is_part_of_the_canonical_brand_asset():
    generator = read("scripts/generate_workspace_brand_asset.py")

    assert 'TAGLINE = "AN AI WORKSPACE FOR WORK THAT CONTINUES"' in generator
    assert 'WORDMARK = ROOT / "public" / "assets" / "brand" / "crump-horizontal-light.png"' in generator
