from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        self.links.append({key: value or "" for key, value in attrs})


def links(relative: str) -> list[dict[str, str]]:
    parser = _LinkParser()
    parser.feed(read(relative))
    return parser.links


def test_public_creation_pages_send_non_book_outputs_to_projects_files():
    expected = {
        "public/ai-document-generator.html": "Choose Keep in a Project",
        "public/ai-resume-builder.html": "Choose Keep in a Project",
        "public/ai-video-generator.html": "Projects → Files",
    }
    for relative, delivery_copy in expected.items():
        page = read(relative)
        assert delivery_copy in page
        assert "private Library" not in page
        assert "private library" not in page

    registration = read("public/auth-controller.js")
    assert "find completed clips in Projects → Files" in registration
    assert "keep completed clips in your private Library" not in registration


def test_homepage_preview_names_all_six_real_destinations_and_their_boundaries():
    page = read("public/ask-crump.html")
    styles = read("public/landing-5.6.css")

    for destination in ("Ask", "Projects", "Create", "Video", "Library", "You"):
        assert f"<small>{destination}</small>" in page
        assert f"<strong>{destination}</strong>" in page
    assert "Projects → Files" in page
    assert "Library remains the private bookshelf for manuscripts and books." in page
    assert "Keep completed clips in your private library" not in page
    assert ".stage-destinations" in styles
    assert ".stage-card.account" in styles


def test_public_creation_ctas_preserve_the_exact_workspace_promise():
    expected_intents = {
        "public/ai-document-generator.html": "document",
        "public/ai-presentation-maker.html": "presentation",
        "public/ai-project-workspace.html": "projects",
        "public/ai-resume-builder.html": "resume",
        "public/ai-video-generator.html": "video",
    }

    for relative, expected_intent in expected_intents.items():
        ctas = [link for link in links(relative) if link.get("data-cta")]
        assert ctas, f"{relative} must expose at least one account-entry action"
        for cta in ctas:
            destination = urlsplit(cta["href"])
            query = parse_qs(destination.query)
            assert destination.path == "/app"
            assert query.get("intent") == [expected_intent]
            assert query.get("plan") == [cta["data-plan"]]
            if "signin" in cta["data-cta"]:
                assert "signup" not in query
            else:
                assert query.get("signup") == ["1"]


def test_homepage_video_button_opens_video_studio_after_account_entry():
    video_ctas = [
        link for link in links("public/ask-crump.html")
        if link.get("data-cta") == "video"
    ]

    assert len(video_ctas) == 1
    destination = urlsplit(video_ctas[0]["href"])
    query = parse_qs(destination.query)
    assert destination.path == "/app"
    assert query == {
        "signup": ["1"],
        "source": ["video"],
        "plan": ["professional"],
        "intent": ["video"],
    }

    controller = read("public/auth-controller.js")
    assert "title: 'Open your Video Studio.'" in controller
    assert "find completed clips in Projects → Files" in controller
    assert "button.textContent = plan?.button || (creation ? 'Create account & continue' : 'Create free account');" in controller


def test_truthful_destination_assets_and_sitemaps_share_one_release_boundary():
    version = "5.9.76-referral-context-1"
    for relative in (
        "public/ask-crump.html",
        "public/ai-project-workspace.html",
        "public/ai-presentation-maker.html",
        "public/ai-document-generator.html",
        "public/ai-resume-builder.html",
        "public/ai-video-generator.html",
    ):
        assert f'/landing-5.6.css?v={version}' in read(relative)

    worker = read("public/sw.js")
    assert "ask-crump-new-body-v1-r226" in worker
    assert f"/landing-5.6.css?v={version}" in worker
    sitemap = read("public/sitemap.xml")
    assert sitemap.count("<lastmod>2026-08-30</lastmod>") == 6
    assert sitemap.count("<lastmod>2026-09-08</lastmod>") == 3
    assert "<lastmod>2026-08-30</lastmod>" in read("public/clever-crump-sitemap.xml")


def test_you_exposes_the_monitored_product_support_address():
    app = read("public/app.html")
    config = read("backend/config.py")
    email_service = read("backend/email_service.py")

    assert 'Product guidance, support, legal information' in app
    assert 'href="mailto:askcrump@gmail.com?subject=Ask%20Crump%20support"' in app
    assert '<div class="settings-label settings-link-label">Product support</div>' in app
    assert '<div class="settings-help">Email askcrump@gmail.com</div>' in app
    assert "monitored = 'askcrump@gmail.com'" in config
    assert "support_email=_support_email(os.getenv('SUPPORT_EMAIL'))" in config
    assert 'self.settings.support_email' in email_service
