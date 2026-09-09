from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct


ROOT = Path(__file__).resolve().parents[1]


GUIDES = {
    "rough-idea-six-week-launch-plan": {
        "title": "How to Turn a Rough Idea Into a Six-Week Launch Plan | Ask Crump",
        "description": "See a real Ask Crump workflow turn a rough event idea, six-week deadline, and $3,000 budget into milestones, risks, and a next action.",
        "campaign": "rough-idea-launch-plan",
        "intent": "projects",
        "destination": "/ai-project-workspace",
        "adjacent": "/guides/what-ai-project-should-remember",
        "modified": "2026-09-08",
        "updated": "September 8, 2026",
        "guide_css": "5.9.76-guide-proof-to-start-1",
        "og_width": 1280,
        "og_height": 720,
    },
    "what-ai-project-should-remember": {
        "title": "What Should an AI Project Remember? | Ask Crump",
        "description": "A practical framework for deciding which instructions, evidence, decisions, conversations, and files belong in a persistent AI Project.",
        "campaign": "project-memory-boundaries",
        "intent": "projects",
        "destination": "/ai-project-workspace",
        "adjacent": "/guides/rough-idea-six-week-launch-plan",
        "modified": "2026-09-08",
        "updated": "September 8, 2026",
        "guide_css": "5.9.76-guide-start-paths-1",
        "og_width": 1280,
        "og_height": 720,
    },
    "editable-ai-powerpoint-review": {
        "title": "Editable AI PowerPoint: A Seven-Pass Review Checklist | Ask Crump",
        "description": "See what editable PowerPoint means in practice and use a seven-pass checklist to review story, evidence, charts, native elements, brand, and accessibility.",
        "campaign": "editable-powerpoint-review",
        "intent": "presentation",
        "destination": "/ai-presentation-maker",
        "adjacent": "/ai-presentation-maker",
        "modified": "2026-09-08",
        "updated": "September 8, 2026",
        "guide_css": "5.9.76-guide-start-paths-1",
        "og_width": 1265,
        "og_height": 712,
    },
}


ASSET_HASHES = {
    "rough-idea-prompt.png": "927E28F77990866218970EFA9E1BA5C4E4B90BDEDD004220FBF402400C870DF5",
    "rough-idea-response.png": "9D3C78858C63640AA3ACE169F4A93E8F04652519AACA48301D418FB259508224",
    "savannah-project.png": "557FA9B8A30664EA8C9CB4C038C62814D460C3B26BA703FEC08B92B431EB31D4",
    "presentation-proof-page.png": "BD3584F508CC82F06AFFEF4AA2713AA59BA58229FFF133588247F5D8D33CCB3A",
    "presentation-title.png": "1AF47A76AC86951B4E244EA2ACF0B168E2CFDC8F1F3AE909F6B5D549775AB85D",
    "presentation-chart.png": "CD806EE318A086181CCCABD51407A8CB5CF0B63B45B79AAB6659FC7E81F07C24",
    "presentation-story.png": "E88EE037D5DFA20CD8C3E2B4A8DD035F1A68548FF45905A839CE5A9D91D3C8E8",
}


RECOVERED_ASSET_DIMENSIONS = {
    "rough-idea-prompt.png": (1280, 720),
    "rough-idea-response.png": (1280, 720),
    "savannah-project.png": (1280, 720),
}


RECOVERED_ASSET_VERSION = "20260907-guide-current-1"


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_search_guides_have_self_referencing_editorial_metadata_and_one_matched_cta():
    for slug, expected in GUIDES.items():
        page = read(f"public/guides/{slug}.html")
        canonical = f"https://www.askcrump.com/guides/{slug}"

        assert f"<title>{expected['title']}</title>" in page
        assert f'<meta name="description" content="{expected["description"]}">' in page
        assert f'<link rel="canonical" href="{canonical}">' in page
        assert f'<meta property="og:url" content="{canonical}">' in page
        assert '<meta property="og:type" content="article">' in page
        assert f'<meta property="og:image:width" content="{expected["og_width"]}">' in page
        assert f'<meta property="og:image:height" content="{expected["og_height"]}">' in page
        assert '<meta name="robots" content="index,follow,max-image-preview:large">' in page
        assert '<meta property="article:published_time" content="2026-08-30">' in page
        assert f'<meta property="article:modified_time" content="{expected["modified"]}">' in page
        assert '<script defer src="/landing.js?v=5.9.76-paid-attribution-1"></script>' in page
        assert f'<link rel="stylesheet" href="/guide.css?v={expected["guide_css"]}">' in page
        assert '/_vercel/insights/script.js' in page
        assert '/_vercel/speed-insights/script.js' in page
        assert page.count("<h1>") == 1
        assert page.count('class="button primary"') == 2
        assert "By <strong>Clever Crump</strong>" in page
        assert "Created <strong>August 30, 2026</strong>" in page
        assert f'Updated <strong>{expected["updated"]}</strong>' in page
        assert "Evidence and method" in page
        assert "Human-review limit" in page
        assert "customer" in page.lower()
        assert f'href="{expected["adjacent"]}"' in page
        assert (
            f'href="{expected["destination"]}?acquisition=organic-search&amp;'
            f'source=workflow-guide&amp;campaign={expected["campaign"]}&amp;creative=search-article"'
        ) in page
        assert "AI VIRTUAL ASSISTANT" not in page
        assert "FAQPage" not in page and '"@type": "HowTo"' not in page

        structured_block = page.split('<script type="application/ld+json">', 1)[1].split("</script>", 1)[0]
        structured = json.loads(structured_block)
        assert structured["@type"] == "Article"
        assert structured["url"] == canonical
        assert structured["mainEntityOfPage"] == canonical
        assert structured["author"]["name"] == "Clever Crump"
        assert structured["datePublished"] == "2026-08-30"
        assert structured["dateModified"] == expected["modified"]


def test_search_guides_expose_early_attribution_preserving_start_paths():
    early_starts = {
        "rough-idea-six-week-launch-plan": {
            "key": "rough-idea",
            "intent": "projects",
            "label": "Start free with your rough idea",
            "support": "Start free with 2 private Projects · No card required",
        },
        "what-ai-project-should-remember": {
            "key": "project-memory",
            "intent": "projects",
            "label": "Start free with a Project",
            "support": "Start free with 2 private Projects · No card required",
        },
        "editable-ai-powerpoint-review": {
            "key": "editable-powerpoint",
            "intent": "presentation",
            "label": "Start an editable presentation",
            "support": "Start free · No card required",
        },
    }

    for slug, expected in early_starts.items():
        page = read(f"public/guides/{slug}.html")
        hero = page.split('<header class="guide-hero">', 1)[1].split("</header>", 1)[0]
        nav = page.split('<nav class="navbar"', 1)[1].split("</nav>", 1)[0]
        hero_cta = (
            f'<a class="button primary" data-cta="{expected["key"]}-hero" data-plan="free" '
            f'href="/app?signup=1&amp;source={expected["key"]}-hero&amp;plan=free&amp;'
            f'intent={expected["intent"]}&amp;acquisition=direct">{expected["label"]}</a>'
        )
        nav_cta = (
            f'class="nav-cta" data-cta="{expected["key"]}-nav" data-plan="free" '
            f'href="/app?signup=1&amp;source={expected["key"]}-nav&amp;plan=free&amp;'
            f'intent={expected["intent"]}&amp;acquisition=direct">Start free</a>'
        )

        assert hero_cta in hero
        assert nav_cta in nav
        assert expected["support"] in hero
        assert hero.index(hero_cta) < hero.index('class="guide-meta"')
        assert "campaign=" not in hero_cta and "creative=" not in hero_cta
        assert page.count(f'data-cta="{expected["key"]}-hero"') == 1
        assert page.count(f'data-cta="{expected["key"]}-nav"') == 1

    landing = read("public/landing.js")
    for marker in (
        "document.querySelectorAll('[data-cta]')",
        "destination.searchParams.set('acquisition', attribution.acquisition)",
        "destination.searchParams.set('campaign', attribution.campaign)",
        "destination.searchParams.set('creative', attribution.creative)",
    ):
        assert marker in landing

    css = read("public/guide.css")
    assert ".guide-hero-actions" in css
    assert "justify-content: flex-start" in css
    assert ".guide-hero-foot" in css

    verifier = read("scripts/verify-search-guide-start-paths.cjs")
    assert "viewport: { width: 390, height: 844 }" in verifier
    assert "all three guides expose responsive phone-width actions" in verifier
    for slug, expected in early_starts.items():
        assert f"path: '/guides/{slug}'" in verifier
        assert f"key: '{expected['key']}'" in verifier


def test_search_guide_assets_are_the_approved_authentic_evidence():
    asset_root = ROOT / "public" / "assets" / "guides"
    for name, expected_hash in ASSET_HASHES.items():
        asset = asset_root / name
        assert asset.is_file() and asset.stat().st_size > 0
        assert hashlib.sha256(asset.read_bytes()).hexdigest().upper() == expected_hash


def test_recovered_guide_asset_dimensions_match_html_and_social_metadata():
    asset_root = ROOT / "public" / "assets" / "guides"
    rough_guide = read("public/guides/rough-idea-six-week-launch-plan.html")
    project_guide = read("public/guides/what-ai-project-should-remember.html")

    for name, expected_dimensions in RECOVERED_ASSET_DIMENSIONS.items():
        payload = (asset_root / name).read_bytes()
        assert payload[:8] == b"\x89PNG\r\n\x1a\n"
        assert struct.unpack(">II", payload[16:24]) == expected_dimensions

    for page in (rough_guide, project_guide):
        assert '<meta property="og:image:width" content="1280">' in page
        assert '<meta property="og:image:height" content="720">' in page

    for name in RECOVERED_ASSET_DIMENSIONS:
        versioned_source = (
            f'src="/assets/guides/{name}?v={RECOVERED_ASSET_VERSION}" '
            'width="1280" height="720"'
        )
        assert versioned_source in rough_guide or (
            name == "savannah-project.png"
            and versioned_source in project_guide
        )

        unversioned_source = f'src="/assets/guides/{name}"'
        assert unversioned_source not in rough_guide
        assert unversioned_source not in project_guide

    assert rough_guide.count(f"?v={RECOVERED_ASSET_VERSION}") == 6
    assert project_guide.count(f"?v={RECOVERED_ASSET_VERSION}") == 4

    assert (
        'alt="The live Ask Crump response showing budget items and six weekly milestones '
        'for the fictional launch plan"'
    ) in rough_guide
    assert "one-sentence strategy and opening launch-plan details" not in rough_guide


def test_search_guides_are_discoverable_and_have_one_canonical_domain():
    sitemap = read("public/sitemap.xml")
    config = json.loads(read("vercel.json"))
    project_page = read("public/ai-project-workspace.html")
    presentation_page = read("public/ai-presentation-maker.html")

    for slug in GUIDES:
        assert sitemap.count(f"<loc>https://www.askcrump.com/guides/{slug}</loc>") == 1
        entry = sitemap.split(f"<loc>https://www.askcrump.com/guides/{slug}</loc>", 1)[1].split("</url>", 1)[0]
        assert f"<lastmod>{GUIDES[slug]['modified']}</lastmod>" in entry

    redirect = next(
        item for item in config["redirects"]
        if item["source"] == "/guides/editable-powerpoint-review-checklist"
    )
    assert redirect == {
        "source": "/guides/editable-powerpoint-review-checklist",
        "destination": "https://www.askcrump.com/guides/editable-ai-powerpoint-review",
        "permanent": True,
    }
    clever_redirect = next(item for item in config["redirects"] if item["source"] == "/guides/:path*")
    assert clever_redirect["destination"] == "https://www.askcrump.com/guides/:path*"
    assert clever_redirect["has"] == [{"type": "host", "value": "www.clevercrump.com"}]
    assert "/guides/rough-idea-six-week-launch-plan" in project_page
    assert "/guides/what-ai-project-should-remember" in project_page
    assert "/guides/editable-ai-powerpoint-review" in presentation_page


def test_search_guide_paths_supply_intent_and_only_default_campaign_for_search():
    landing = read("public/landing.js")
    checker = read("scripts/check-javascript.mjs")

    for slug, expected in GUIDES.items():
        assert f"'/guides/{slug}': '{expected['intent']}'" in landing
        assert f"campaign: '{expected['campaign']}'" in landing

    assert "detectedAcquisition === 'organic'" in landing
    assert "? 'organic-search'" in landing
    assert "pageCampaignEligible = Boolean(pageCampaign && acquisition === 'organic-search')" in landing
    assert "stored ? normalizeAttribution(stored) : candidate" in landing
    assert "Canonical organic-search guide entry" in checker
    assert "Organic social to guide to capability" in checker
    assert "intent=projects" not in checker.split(
        "https://askcrump.com/guides/what-ai-project-should-remember?", 1
    )[1].split("'", 1)[0]


def test_search_guide_layout_has_bounded_phone_width_media():
    css = read("public/guide.css")

    assert "@media (max-width: 620px)" in css
    assert "width: calc(100% - 36px)" in css
    assert ".guide-slide-grid { grid-template-columns: 1fr; }" in css
    assert ".guide-media-frame img" in css
    assert "width: 100%" in css and "height: auto" in css
    assert "overflow-wrap: anywhere" in css
