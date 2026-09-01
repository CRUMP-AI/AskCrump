from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


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


def test_truthful_destination_assets_and_sitemaps_share_one_release_boundary():
    version = "5.9.76-truthful-destinations-1"
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
    assert "ask-crump-new-body-v1-r208" in worker
    assert f"/landing-5.6.css?v={version}" in worker
    assert read("public/sitemap.xml").count("<lastmod>2026-08-30</lastmod>") == 9
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
