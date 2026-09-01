from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LANDING = ROOT / "public" / "landing.js"
TELEMETRY = ROOT / "public" / "telemetry-config.js"


def test_marketing_landing_event_is_content_free_and_once_per_tab():
    source = LANDING.read_text(encoding="utf-8")
    event_block = source[
        source.index("function emitMarketingLanding"):
        source.index("const attribution = firstTouchAttribution()")
    ]

    assert "const MARKETING_LANDING_KEY = 'askcrump.marketing-landing-emitted'" in source
    assert "sessionStorage.getItem(MARKETING_LANDING_KEY)" in event_block
    assert "sessionStorage.setItem(MARKETING_LANDING_KEY, '1')" in event_block
    assert "name: 'MarketingLanding'" in event_block
    assert "touchpoint," in event_block
    assert "intent: attribution.intent || 'unspecified'" in event_block
    assert "...attribution" not in event_block
    for forbidden in ("user_id", "email", "prompt", "response", "filename", "referrer", "url:"):
        assert forbidden not in event_block


def test_marketing_landing_requires_an_exact_allowlisted_touchpoint():
    source = LANDING.read_text(encoding="utf-8")
    touchpoint_block = source[
        source.index("function marketingLandingTouchpoint"):
        source.index("function emitMarketingLanding")
    ]

    assert "marketingLandingKind === 'exact-referral'" in touchpoint_block
    assert "marketingLandingKind !== 'registered-campaign'" in touchpoint_block
    assert "return 'referral.response-share'" in touchpoint_block
    assert "CAMPAIGN_REGISTRY[attribution.campaign]" in touchpoint_block
    assert "specification.acquisitions.has(attribution.acquisition)" in touchpoint_block
    assert "specification.placements.has(attribution.placement)" in touchpoint_block
    assert "specification.creatives.has(attribution.creative)" in touchpoint_block
    assert "specification.intent !== attribution.intent" in touchpoint_block
    assert "].join('.')" in touchpoint_block


def test_referral_eligibility_preserves_parameter_presence_without_raw_values():
    source = LANDING.read_text(encoding="utf-8")
    validity_block = source[
        source.index("function explicitAttributionInputsValid"):
        source.index("function currentAttribution")
    ]
    current_block = source[
        source.index("function currentAttribution"):
        source.index("function storedFirstTouch")
    ]
    first_touch_block = source[
        source.index("function storedFirstTouch"):
        source.index("function marketingLandingTouchpoint")
    ]

    assert "for (const key of ['acquisition', 'utm_source'])" in validity_block
    assert "params.has('source')" in validity_block
    assert "params.has('campaign')" in validity_block
    assert "params.has('creative')" in validity_block
    assert "params.has('intent')" in validity_block
    assert "CREATION_INTENTS.has(tokenValue(params.get('intent')))" in validity_block
    assert "const explicitInputsValid = explicitAttributionInputsValid(params)" in current_block
    assert "!params.has('campaign')" in current_block
    assert "!params.has('creative')" in current_block
    assert "explicitInputsValid && attribution.campaign && attribution.creative" in current_block
    assert "exactReferral ? 'exact-referral' : 'rejected'" in current_block
    assert "marketingLandingKind: firstTouchMarketingKind" in first_touch_block
    assert "stored?.marketingLandingKind" in first_touch_block
    assert "params.get('campaign')" not in first_touch_block
    assert "params.get('creative')" not in first_touch_block


def test_pageview_redaction_remains_enabled_before_landing_runtime():
    telemetry = TELEMETRY.read_text(encoding="utf-8")
    assert "url.search = '';" in telemetry
    assert "url.hash = '';" in telemetry
    assert "window.va('beforeSend', sanitizedEvent)" in telemetry

    pages = [
        ROOT / "public" / "ask-crump.html",
        *sorted((ROOT / "public").glob("ai-*.html")),
        *sorted((ROOT / "public" / "guides").glob("*.html")),
    ]
    for page_path in pages:
        page = page_path.read_text(encoding="utf-8")
        assert page.index("/telemetry-config.js") < page.index("/landing.js")


def test_marketing_landing_never_enters_product_or_account_storage():
    backend = (ROOT / "backend" / "product_analytics.py").read_text(encoding="utf-8")
    migrations = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((ROOT / "migrations").glob("*.sql"))
    )
    controller = (ROOT / "public" / "auth-controller.js").read_text(encoding="utf-8")

    assert "MarketingLanding" not in backend
    assert "marketinglanding" not in migrations.lower()
    assert "MarketingLanding" not in controller
