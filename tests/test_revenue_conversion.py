import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def read_json_ld(page: str) -> dict:
    blocks = re.findall(
        r'<script type="application/ld\+json">\s*(.*?)\s*</script>',
        page,
        flags=re.DOTALL,
    )
    assert len(blocks) == 1
    return json.loads(blocks[0])


def contrast_ratio(foreground: str, background: str) -> float:
    def luminance(color: str) -> float:
        channels = [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
        linear = [
            channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4
            for channel in channels
        ]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    lighter, darker = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def rule_color(css: str, selector: str) -> str:
    rule = re.search(rf"{re.escape(selector)}\s*\{{([^}}]+)\}}", css)
    assert rule, f"Missing CSS rule for {selector}"
    color = re.search(r"(?:^|;)\s*color:\s*(#[0-9a-fA-F]{6})", rule.group(1))
    assert color, f"Missing text color for {selector}"
    return color.group(1)


def test_marketing_page_exposes_a_clear_free_to_paid_path():
    page = read("public/ask-crump.html")

    assert 'id="pricing"' in page
    assert "Clear pricing. Real runway." in page
    assert "$0" in page and "$20" in page and "$50" in page
    assert "50 · $4.99" in page and "400 · $19.99" in page
    assert "No card required" in page
    assert "eventually choose to pay" not in page
    for plan in ("free", "professional", "enterprise"):
        assert f"plan={plan}" in page
    assert page.count('data-cta="') >= 7


def test_marketing_ctas_are_first_party_analytics_events():
    page = read("public/ask-crump.html")
    script = read("public/landing.js")

    assert '/_vercel/insights/script.js' in page
    assert '/_vercel/speed-insights/script.js' in page
    assert '<script defer src="/landing.js?v=5.9.76-referral-1"></script>' in page
    assert '<link rel="stylesheet" href="/landing-5.6.css?v=5.9.76-1">' in page
    assert "window.vaq" in script
    assert "MarketingCTA" in script
    assert "MarketingSignin" in script
    assert "destination.searchParams.get('signup') === '1'" in script
    assert "link.dataset.cta" in script
    assert "link.dataset.plan" in script
    assert "utm_source" in script
    assert "destination.searchParams.set('acquisition', acquisition)" in script
    assert "new Set(['response-share'])" in script
    assert "destination.searchParams.set('source', placement)" in script
    assert "sessionStorage.setItem(ACQUISITION_PLACEMENT_KEY" in script
    assert "sessionStorage.setItem(ACQUISITION_KEY" in script
    assert "document.referrer" in script
    assert "referrer URL" not in script
    assert 'data-explore="product-preview"' in page
    assert "MarketingExplore" in script
    assert "link.dataset.explore" in script
    assert "window.location.replace('/app')" not in script
    assert 'rel="canonical" href="https://www.askcrump.com/"' in page
    assert 'property="og:title"' in page
    assert 'type="application/ld+json"' in page
    assert 'class="nav-signin"' in page
    assert 'href="/app?signup=1' in page
    assert 'href="https://askcrump.com/app' not in page


def test_known_search_referrers_are_privacy_minimized_as_organic():
    script = read("public/landing.js")
    controller = read("public/auth-controller.js")

    assert "'organic'" in script
    assert "google\\.[a-z.]+" in script
    for host in ("bing.com", "duckduckgo.com", "search.yahoo.com", "ecosia.org", "search.brave.com"):
        assert host in script
    assert "return 'organic'" in script
    assert "LEGACY_ACQUISITION_SOURCES.has(legacySource)" in script
    assert "'organic'" in controller
    assert "referrer URL" not in script


def test_public_marketing_surface_is_indexable_while_the_private_app_is_not():
    page = read("public/ask-crump.html")
    app = read("public/app.html")
    legal = read("public/legal.html")
    robots = read("public/robots.txt")
    sitemap = read("public/sitemap.xml")

    assert 'name="robots" content="index,follow' in page
    assert 'name="robots" content="noindex,nofollow"' in app
    assert "Sitemap: https://www.askcrump.com/sitemap.xml" in robots
    assert "Disallow: /app" in robots and "Disallow: /api/" in robots
    assert "<loc>https://www.askcrump.com/</loc>" in sitemap
    assert '<meta name="robots" content="index,follow,max-image-preview:large">' in legal
    assert '<link rel="canonical" href="https://www.askcrump.com/legal">' in legal
    assert '<a href="/legal">Legal & Privacy</a>' in page
    assert "<loc>https://www.askcrump.com/legal</loc>" in sitemap
    assert "<loc>https://www.askcrump.com/legal.html</loc>" not in sitemap
    assert "<loc>https://www.askcrump.com/ai-presentation-maker</loc>" in sitemap
    assert "<loc>https://www.askcrump.com/ai-document-generator</loc>" in sitemap
    assert "<loc>https://www.askcrump.com/ai-resume-builder</loc>" in sitemap
    assert "<loc>https://www.askcrump.com/ai-video-generator</loc>" in sitemap
    assert sitemap.count("<lastmod>2026-08-27</lastmod>") == 3
    assert sitemap.count("<lastmod>2026-08-29</lastmod>") == 2
    assert sitemap.count("<lastmod>2026-08-24</lastmod>") == 1

    namespace = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    parsed = ET.fromstring(sitemap)
    urls = {
        entry.findtext("sm:loc", namespaces=namespace): entry.findtext("sm:lastmod", namespaces=namespace)
        for entry in parsed.findall("sm:url", namespace)
    }
    assert urls == {
        "https://www.askcrump.com/": "2026-08-27",
        "https://www.askcrump.com/ai-presentation-maker": "2026-08-27",
        "https://www.askcrump.com/ai-document-generator": "2026-08-29",
        "https://www.askcrump.com/ai-resume-builder": "2026-08-29",
        "https://www.askcrump.com/ai-video-generator": "2026-08-27",
        "https://www.askcrump.com/legal": "2026-08-24",
    }


def test_use_case_pages_are_unique_crawlable_and_attribution_ready():
    home = read("public/ask-crump.html")
    presentation = read("public/ai-presentation-maker.html")
    document = read("public/ai-document-generator.html")
    resume = read("public/ai-resume-builder.html")
    video = read("public/ai-video-generator.html")

    assert 'id="use-cases"' in home
    assert 'data-explore="presentation-page"' in home
    assert 'data-explore="document-page"' in home
    assert 'data-explore="resume-page"' in home
    assert 'data-explore="video-page"' in home
    assert 'href="/ai-presentation-maker"' in home
    assert 'href="/ai-document-generator"' in home
    assert 'href="/ai-resume-builder"' in home
    assert 'href="/ai-video-generator"' in home

    expectations = (
        (presentation, "AI Presentation Maker for Editable PowerPoint", "ai-presentation-maker", "presentation-hero", ".pptx"),
        (document, "AI Document Generator for Word and PDF", "ai-document-generator", "document-hero", ".docx"),
        (resume, "AI Resume Builder for Editable Word Resumes", "ai-resume-builder", "resume-hero", ".docx"),
        (video, "AI Video Generator for Short Creative Scenes", "ai-video-generator", "video-page-hero", "Crump Credits"),
    )
    titles = set()
    descriptions = set()
    for page, title, slug, source, file_type in expectations:
        assert f"<title>{title} | Ask Crump</title>" in page
        assert f'<link rel="canonical" href="https://www.askcrump.com/{slug}">' in page
        assert f'<meta property="og:url" content="https://www.askcrump.com/{slug}">' in page
        assert '<meta name="robots" content="index,follow,max-image-preview:large">' in page
        assert '<script defer src="/landing.js?v=5.9.76-referral-1"></script>' in page
        assert '<link rel="stylesheet" href="/landing-5.6.css?v=5.9.76-1">' in page
        assert '<link rel="stylesheet" href="/use-case.css?v=5.9.76">' in page
        assert '/_vercel/insights/script.js' in page
        assert '/_vercel/speed-insights/script.js' in page
        assert f'source={source}' in page
        assert page.count('data-cta="') >= 4
        assert file_type in page
        assert "review" in page.lower()
        assert "acquisition=organic" not in page

        title_match = re.search(r"<title>(.*?)</title>", page)
        description_match = re.search(r'<meta name="description" content="([^"]+)">', page)
        assert title_match and description_match
        titles.add(title_match.group(1))
        descriptions.add(description_match.group(1))

        structured_data = read_json_ld(page)
        assert structured_data["@context"] == "https://schema.org"
        graph = structured_data["@graph"]
        assert graph[0]["@type"] == "WebPage"
        assert graph[0]["url"] == f"https://www.askcrump.com/{slug}"
        assert graph[1]["@type"] == "SoftwareApplication"
        assert graph[1]["offers"]["price"] == "0"

    assert len(titles) == 4
    assert len(descriptions) == 4


def test_real_user_performance_measurement_covers_growth_surfaces_once():
    pages = {
        "public/ask-crump.html": "/",
        "public/ai-presentation-maker.html": "/ai-presentation-maker",
        "public/ai-document-generator.html": "/ai-document-generator",
        "public/ai-resume-builder.html": "/ai-resume-builder",
        "public/ai-video-generator.html": "/ai-video-generator",
        "public/app.html": "/app",
        "public/clever-crump.html": "/clever-crump",
    }

    for relative, route in pages.items():
        page = read(relative)
        privacy_config = 'src="/telemetry-config.js?v=5.9.76"'
        web_analytics = 'src="/_vercel/insights/script.js"'
        collector = (
            f'src="/_vercel/speed-insights/script.js" data-route="{route}"'
        )
        assert page.count('/telemetry-config.js') == 1
        assert page.count('/_vercel/insights/script.js') == 1
        assert page.count('/_vercel/speed-insights/script.js') == 1
        assert privacy_config in page
        assert web_analytics in page
        assert collector in page
        assert page.index(privacy_config) < page.index(web_analytics)
        assert page.index(privacy_config) < page.index(collector)


def test_vercel_telemetry_strips_query_and_fragment_before_transmission():
    config = read("public/telemetry-config.js")
    controller = read("public/auth-controller.js")

    assert "params.get('token')" in controller
    assert "window.va('beforeSend'" in config
    assert "window.si('beforeSend'" in config
    assert "url.search = ''" in config
    assert "url.hash = ''" in config
    assert "return null" in config


def test_presentation_page_proves_output_with_synthetic_rendered_examples():
    page = read("public/ai-presentation-maker.html")
    styles = read("public/use-case.css")
    example_names = (
        "presentation-title.png",
        "presentation-story.png",
        "presentation-chart.png",
    )

    assert 'id="representative-output"' in page
    assert "Judge the slide, not the promise." in page
    assert "current PowerPoint exporter" in page
    assert "actual visual system—not a hand-designed concept" in page
    assert "Representative synthetic output." in page
    assert "no customer content or testimonial is shown" in page
    assert 'class="presentation-proof-grid"' in page
    assert ".presentation-proof-layout" in styles
    assert ".presentation-proof-grid" in styles
    assert "grid-template-columns: 1.28fr .72fr" in styles

    for filename in example_names:
        assert f'/assets/examples/{filename}' in page
        with Image.open(ROOT / "public" / "assets" / "examples" / filename) as example:
            assert example.format == "PNG"
            assert example.mode in {"RGB", "RGBA"}
            assert example.size == (1600, 900)


def test_resume_page_proves_output_with_a_synthetic_rendered_example():
    page = read("public/ai-resume-builder.html")
    styles = read("public/use-case.css")
    example_path = ROOT / "public" / "assets" / "examples" / "resume-product-operations.png"

    assert 'id="representative-output"' in page
    assert "See the résumé, not just the promise." in page
    assert "current Word exporter" in page
    assert "actual editable .docx structure—not a hand-designed mockup" in page
    assert "Representative synthetic output." in page
    assert "no customer content or testimonial is shown" in page
    assert 'data-cta="resume-proof"' in page
    assert 'source=resume-proof' in page
    assert 'intent=resume' in page
    assert 'href="/assets/examples/resume-product-operations.png"' in page
    assert ".artifact-proof-layout" in styles
    assert ".artifact-proof-open:focus-visible" in styles
    assert "grid-template-columns: minmax(0, .88fr) minmax(420px, .82fr)" in styles

    with Image.open(example_path) as example:
        assert example.format == "PNG"
        assert example.mode in {"RGB", "RGBA"}
        assert example.size == (1275, 1650)


def test_document_page_proves_output_with_a_synthetic_rendered_example():
    page = read("public/ai-document-generator.html")
    styles = read("public/use-case.css")
    example_path = ROOT / "public" / "assets" / "examples" / "document-launch-readiness.png"

    assert 'id="representative-output"' in page
    assert "Inspect the work before you start." in page
    assert "current Word exporter" in page
    assert "actual editable .docx structure—not a hand-designed mockup" in page
    assert "Representative synthetic output." in page
    assert "no customer content or testimonial is shown" in page
    assert 'data-cta="document-proof"' in page
    assert 'source=document-proof' in page
    assert 'intent=document' in page
    assert 'href="/assets/examples/document-launch-readiness.png"' in page
    assert ".artifact-proof-layout" in styles
    assert ".artifact-proof-open:focus-visible" in styles
    assert "grid-template-columns: minmax(0, .88fr) minmax(420px, .82fr)" in styles

    with Image.open(example_path) as example:
        assert example.format == "PNG"
        assert example.mode in {"RGB", "RGBA"}
        assert example.size == (1224, 1584)


def test_social_share_cards_are_large_brand_safe_and_page_specific():
    expectations = (
        ("public/ask-crump.html", "ask-crump-workspace.png"),
        ("public/ai-presentation-maker.html", "ask-crump-presentations.png"),
        ("public/ai-document-generator.html", "ask-crump-documents.png"),
        ("public/ai-resume-builder.html", "ask-crump-resumes.png"),
        ("public/ai-video-generator.html", "ask-crump-video.png"),
    )

    for page_path, filename in expectations:
        page = read(page_path)
        card_path = ROOT / "public" / "assets" / "social" / filename

        assert f'https://www.askcrump.com/assets/social/{filename}' in page
        assert '<meta property="og:image:type" content="image/png">' in page
        assert '<meta property="og:image:width" content="1200">' in page
        assert '<meta property="og:image:height" content="630">' in page
        assert '<meta name="twitter:card" content="summary_large_image">' in page
        assert '<meta name="twitter:image:alt"' in page
        with Image.open(card_path) as card:
            assert card.format == "PNG"
            assert card.mode == "RGB"
            assert card.size == (1200, 630)


def test_social_launch_cards_include_platform_native_portraits():
    expected = (
        "ask-crump-workspace-portrait.png",
        "ask-crump-presentations-portrait.png",
    )
    for filename in expected:
        with Image.open(ROOT / "public" / "assets" / "social" / filename) as card:
            assert card.format == "PNG"
            assert card.mode == "RGB"
            assert card.size == (1080, 1350)


def test_social_launch_batch_uses_contextual_attributed_destinations():
    packet = read("docs/SOCIAL_LAUNCH_BATCH_2026-08-29.md")

    assert "https://www.askcrump.com/?utm_source=facebook" in packet
    assert "https://www.askcrump.com/?utm_source=instagram" in packet
    assert "https://www.askcrump.com/ai-presentation-maker?utm_source=facebook" in packet
    assert "https://www.askcrump.com/ai-presentation-maker?utm_source=instagram" in packet
    assert "https://www.askcrump.com/app" not in packet


def test_public_marketing_text_colors_meet_wcag_aa_contrast():
    landing = read("public/landing-5.6.css")
    use_case = read("public/use-case.css")
    landing_pairs = (
        (".hero-foot", "#070a0e"),
        (".stage-top", "#090d12"),
        (".stage-card span:last-child", "#111820"),
        (".stage-composer", "#151c23"),
        (".engine span", "#0d1319"),
        (".engine em", "#0d1319"),
        (".price span", "#0e141a"),
        (".credit-note div > span", "#0e1318"),
        (".pricing-fineprint", "#0a0f14"),
    )
    for selector, background in landing_pairs:
        assert contrast_ratio(rule_color(landing, selector), background) >= 4.5, selector

    assert contrast_ratio(rule_color(use_case, ".use-case-proof span"), "#0d1319") >= 4.5


def test_signup_deep_link_opens_registration_and_tracks_the_funnel():
    app = read("public/app.html")
    controller = read("public/auth-controller.js")

    assert '/_vercel/insights/script.js' in app
    assert "params.get('signup') === '1'" in controller
    assert "if (signupRequested) {\n      showAuth('register');" in controller
    assert controller.index("showAuth('register');", controller.index("async function bootstrap")) < controller.index("await window.CrumpAPI?.ready")
    assert "function trackSignupIntent(locationName)" in controller
    assert "trackSignupIntent('deep-link')" in controller
    assert "trackFunnel('SignupStarted');" in controller
    assert "trackFunnel('SignupCredentialsReady');" in controller
    assert "SignupSubmitted" in controller
    assert "AccountCreated" in controller
    assert "trackFunnel('RegistrationExplore', {destination});" in controller
    assert "creationIntentValue(link.dataset.exploreDestination) || 'overview'" in controller
    assert "source: funnelContext().acquisition" in controller
    assert "params.get('acquisition')" in controller
    assert "function referringAcquisitionSource()" in controller
    assert "document.referrer" in controller
    assert "host === 'askcrump.com'" in controller
    assert "['facebook.com', 'facebook']" in controller
    assert "['instagram.com', 'instagram']" in controller
    assert "const derivedAcquisition = currentAcquisition || storedAcquisition" in controller
    assert "acquisition: currentAcquisition || storedAcquisition || derivedAcquisition || 'direct'" in controller
    assert "registerEmail" not in controller[controller.index("function trackFunnel"):controller.index("function applyServerSettings")]


def test_legacy_social_deep_links_keep_channel_attribution_without_relabeling_ctas():
    controller = read("public/auth-controller.js")

    assert "LEGACY_ACQUISITION_SOURCES" in controller
    for channel in (
        "instagram",
        "facebook",
        "facebook-pinned",
        "linkedin",
        "tiktok",
        "youtube",
        "x",
        "referral",
        "clevercrump",
    ):
        assert f"'{channel}'" in controller
    assert "LEGACY_ACQUISITION_SOURCES.has(locationSource)" in controller
    assert "const currentAcquisition = explicitAcquisition || legacyAcquisition" in controller
    assert "acquisition: currentAcquisition || storedAcquisition || derivedAcquisition || 'direct'" in controller
    allowlist = controller[
        controller.index("const LEGACY_ACQUISITION_SOURCES"):
        controller.index("window.va =")
    ]
    for onsite_location in ("hero", "pricing", "footer", "closing", "video"):
        assert f"'{onsite_location}'" not in allowlist


def test_paid_plan_intent_survives_auth_and_stops_before_checkout():
    controller = read("public/auth-controller.js")
    runtime = read("public/runtime-body-v1.js")
    subscriptions = read("public/crump-subscriptions-5.3.2.js")

    assert "askcrump.pending-plan-intent" in controller
    assert "PAID_PLAN_INTENTS = new Set(['professional', 'enterprise'])" in controller
    assert "PLAN_INTENT_TTL_MS" in controller
    assert "crump:plan-intent" in controller
    assert "crump:body-runtime-ready" in runtime
    assert "window.showBillingCenter?.({plan})" in subscriptions
    assert "data-crump-plan" in subscriptions or "dataset.crumpPlan" in subscriptions
    assert "PlanIntentReached" in subscriptions
    listener = subscriptions[subscriptions.index("window.addEventListener('crump:plan-intent'"):]
    assert "openCheckout(plan" not in listener
    assert "crump:plan-intent-consumed" in listener


def test_release_version_and_cache_advance_together():
    package = read("package.json")
    backend = read("backend/version.py")
    worker = read("public/sw.js")

    assert '"version": "5.9.76"' in package
    assert "__version__ = '5.9.76'" in backend
    assert "ask-crump-new-body-v1-r125" in worker
    assert "/landing-5.6.css?v=5.9.76-1" in worker
    assert "/use-case.css?v=5.9.76" in worker
    assert "/landing.js?v=5.9.76-referral-1" in worker


def test_changed_activation_assets_are_release_versioned():
    shell = read("public/app.html")
    runtime = read("public/runtime-body-v1.js")
    worker = read("public/sw.js")

    for asset in (
        "/crump-v1-body.css?v=5.9.76",
        "/device-auth.js?v=5.9.76",
        "/auth-controller.js?v=5.9.76-verification-session-1",
    ):
        assert asset in shell
        assert asset in worker

    for asset in (
        "/conversation.css?v=5.9.76",
        "/ui-functions.js?v=5.9.76-referral-1",
        "/product-analytics.js?v=5.9.76",
        "/app.js?v=5.9.76",
    ):
        assert asset not in shell
        assert asset in runtime
        assert asset in worker

    assert "/crump-4.3.js?v=5.9.76" in runtime
    assert "/crump-4.3.js?v=5.9.76" in worker
