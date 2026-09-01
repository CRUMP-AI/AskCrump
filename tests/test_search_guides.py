from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


GUIDES = {
    "rough-idea-six-week-launch-plan": {
        "title": "How to Turn a Rough Idea Into a Six-Week Launch Plan | Ask Crump",
        "description": "See a real Ask Crump workflow turn a rough event idea, six-week deadline, and $3,000 budget into milestones, risks, and a next action.",
        "campaign": "rough-idea-launch-plan",
        "intent": "projects",
        "destination": "/ai-project-workspace",
        "adjacent": "/guides/what-ai-project-should-remember",
    },
    "what-ai-project-should-remember": {
        "title": "What Should an AI Project Remember? | Ask Crump",
        "description": "A practical framework for deciding which instructions, evidence, decisions, conversations, and files belong in a persistent AI Project.",
        "campaign": "project-memory-boundaries",
        "intent": "projects",
        "destination": "/ai-project-workspace",
        "adjacent": "/guides/rough-idea-six-week-launch-plan",
    },
    "editable-ai-powerpoint-review": {
        "title": "Editable AI PowerPoint: A Seven-Pass Review Checklist | Ask Crump",
        "description": "See what editable PowerPoint means in practice and use a seven-pass checklist to review story, evidence, charts, native elements, brand, and accessibility.",
        "campaign": "editable-powerpoint-review",
        "intent": "presentation",
        "destination": "/ai-presentation-maker",
        "adjacent": "/ai-presentation-maker",
    },
}


ASSET_HASHES = {
    "rough-idea-prompt.png": "4CBE40A33DB0CB6D261F22D2038134329D95052C01C7BCCA6B160AC7DFBD663F",
    "rough-idea-response.png": "ED93FCD6C9615A7C34550FF76BDCD2861692ED4E430FAA5774FD0F8DBA4D1D63",
    "savannah-project.png": "A84FC3B9CD385431511537DE1524C968ABE6C956E3DD82BB2D264B4565CFBDBF",
    "presentation-proof-page.png": "BD3584F508CC82F06AFFEF4AA2713AA59BA58229FFF133588247F5D8D33CCB3A",
    "presentation-title.png": "1AF47A76AC86951B4E244EA2ACF0B168E2CFDC8F1F3AE909F6B5D549775AB85D",
    "presentation-chart.png": "CD806EE318A086181CCCABD51407A8CB5CF0B63B45B79AAB6659FC7E81F07C24",
    "presentation-story.png": "E88EE037D5DFA20CD8C3E2B4A8DD035F1A68548FF45905A839CE5A9D91D3C8E8",
}


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
        assert '<meta name="robots" content="index,follow,max-image-preview:large">' in page
        assert '<meta property="article:published_time" content="2026-08-30">' in page
        assert '<meta property="article:modified_time" content="2026-08-30">' in page
        assert '<script defer src="/landing.js?v=5.9.76-marketing-landing-1"></script>' in page
        assert '<link rel="stylesheet" href="/guide.css?v=5.9.76-search-guides-1">' in page
        assert '/_vercel/insights/script.js' in page
        assert '/_vercel/speed-insights/script.js' in page
        assert page.count("<h1>") == 1
        assert page.count('class="button primary"') == 1
        assert "By <strong>Clever Crump</strong>" in page
        assert "Created <strong>August 30, 2026</strong>" in page
        assert "Updated <strong>August 30, 2026</strong>" in page
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


def test_search_guide_assets_are_the_approved_authentic_evidence():
    asset_root = ROOT / "public" / "assets" / "guides"
    for name, expected_hash in ASSET_HASHES.items():
        asset = asset_root / name
        assert asset.is_file() and asset.stat().st_size > 0
        assert hashlib.sha256(asset.read_bytes()).hexdigest().upper() == expected_hash


def test_search_guides_are_discoverable_and_have_one_canonical_domain():
    sitemap = read("public/sitemap.xml")
    config = json.loads(read("vercel.json"))
    project_page = read("public/ai-project-workspace.html")
    presentation_page = read("public/ai-presentation-maker.html")

    for slug in GUIDES:
        assert sitemap.count(f"<loc>https://www.askcrump.com/guides/{slug}</loc>") == 1

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
