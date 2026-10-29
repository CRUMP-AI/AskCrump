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
        "public/ai-video-generator.html": "completed work in Files",
    }
    for relative, delivery_copy in expected.items():
        page = read(relative)
        assert delivery_copy in page
        assert "private Library" not in page
        assert "private library" not in page

    registration = read("public/auth-controller.js")
    assert "find completed clips in Files" in registration
    assert "keep completed clips in your private Library" not in registration


def test_homepage_preview_names_the_friendly_workspace_destinations_and_boundaries():
    page = read("public/ask-crump.html")
    styles = read("public/landing-5.6.css")

    for destination in ("Ask", "Projects", "Files", "Library", "Video", "Autonomous"):
        assert f"<small>{destination}</small>" in page
        assert f"<strong>{destination}</strong>" in page
    assert "<small>Profile</small>" in page
    assert "<strong>Create</strong>" not in page
    assert "<strong>You</strong>" not in page
    assert "What can I help you get done?" in page
    assert "Generated work and uploads live in Files" in page
    assert "Library remains the private bookshelf for manuscripts and books." in page
    assert "Keep completed clips in your private library" not in page
    assert ".stage-destinations" in styles
    assert ".stage-card.account" in styles


def test_public_creation_ctas_preserve_the_exact_workspace_promise():
    expected_intents = {
        "public/ai-document-generator.html": ("document", "professional", "document-free"),
        "public/ai-presentation-maker.html": ("presentation", "professional", "presentation-free"),
        "public/ai-project-workspace.html": ("projects", "professional", "projects-free"),
        "public/ai-resume-builder.html": ("resume", "professional", "resume-free"),
        "public/ai-video-generator.html": ("video", "professional", "video-page-free"),
    }

    for relative, (expected_intent, expected_signup_plan, expected_free_cta) in expected_intents.items():
        ctas = [link for link in links(relative) if link.get("data-cta")]
        assert ctas, f"{relative} must expose at least one account-entry action"
        assert sum(cta["data-cta"] == expected_free_cta for cta in ctas) == 1
        for cta in ctas:
            destination = urlsplit(cta["href"])
            query = parse_qs(destination.query)
            assert destination.path == "/app"
            assert query.get("intent") == [expected_intent]
            assert query.get("plan") == [cta["data-plan"]]
            if "signin" in cta["data-cta"]:
                assert "signup" not in query
            elif cta["data-cta"] == expected_free_cta:
                assert cta["data-plan"] == "free"
                assert query.get("source") == [expected_free_cta]
                assert "signup" not in query
            else:
                assert cta["data-plan"] == expected_signup_plan
                assert query.get("plan") == [expected_signup_plan]
                assert query.get("signup") == ["1"]

    for relative, disclosure in {
        "public/ai-document-generator.html": "Document creation requires a paid plan · Account creation is free · Nothing is purchased until checkout is confirmed",
        "public/ai-presentation-maker.html": "Presentation creation requires a paid plan · Account creation is free · Nothing is purchased until checkout is confirmed",
        "public/ai-project-workspace.html": "Projects require a paid plan · Account creation is free · Nothing is purchased until checkout is confirmed",
        "public/ai-resume-builder.html": "Résumé creation requires a paid plan · Account creation is free · Nothing is purchased until checkout is confirmed",
        "public/ai-video-generator.html": "Video generation uses Crump Credits · Current cost is shown before generation · Availability and output can vary",
    }.items():
        assert disclosure in read(relative)


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
    assert "find completed clips in Files" in controller
    assert "button.textContent = creationKind === 'image'" in controller
    assert ": (plan?.button || (creation ? 'Create account & continue' : 'Create free account'));" in controller


def test_truthful_destination_assets_and_sitemaps_share_one_release_boundary():
    version = "5.9.76-signin-escape-1"
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
    assert "ask-crump-new-body-v1-r280-login-workspace-recovery-2" in worker
    assert f"/landing-5.6.css?v={version}" in worker
    assert "<lastmod>2026-08-30</lastmod>" in read("public/clever-crump-sitemap.xml")


def test_you_exposes_the_monitored_product_support_address():
    app = read("public/app.html")
    config = read("backend/config.py")
    email_service = read("backend/email_service.py")

    assert 'Invite someone, get product support, review legal information' in app
    assert 'Invite someone to Ask Crump' in app
    assert 'href="mailto:askcrump@gmail.com?subject=Ask%20Crump%20support"' in app
    assert '<div class="settings-label settings-link-label">Product support</div>' in app
    assert '<div class="settings-help">Email askcrump@gmail.com</div>' in app
    assert "monitored = 'askcrump@gmail.com'" in config
    assert "support_email=_support_email(os.getenv('SUPPORT_EMAIL'))" in config
    assert 'self.settings.support_email' in email_service


def test_public_contact_routes_use_the_monitored_support_inbox():
    legal = read("public/legal.html")
    deletion = read("public/delete-account.html")
    security = read("SECURITY.md")
    public_pages = (
        "public/ask-crump.html",
        "public/ai-project-workspace.html",
        "public/ai-presentation-maker.html",
        "public/ai-document-generator.html",
        "public/ai-resume-builder.html",
        "public/ai-video-generator.html",
        "public/guides/audit-ai-resume-bullets.html",
        "public/guides/editable-ai-powerpoint-review.html",
        "public/guides/rough-idea-six-week-launch-plan.html",
        "public/guides/what-ai-project-should-remember.html",
        "public/guides/word-or-pdf-ai-document-output.html",
    )

    assert 'Product help: <a href="mailto:askcrump@gmail.com?subject=Ask%20Crump%20support">' in legal
    assert 'mailto:askcrump@gmail.com?subject=Ask%20Crump%20account%20deletion' in deletion
    assert "`askcrump@gmail.com`" in security
    assert "@askcrump.com" not in legal
    assert "@askcrump.com" not in deletion
    assert "@askcrump.com" not in security
    for relative in public_pages:
        assert 'href="/legal#contact">Support</a>' in read(relative)
