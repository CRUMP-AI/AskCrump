from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from backend.product_analytics import ATTRIBUTION_INTENTS, normalize_attribution


ROOT = Path(__file__).resolve().parents[1]


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value or "" for key, value in attrs}
        if tag == "a" and values.get("data-cta") == "image":
            self.links.append(values)


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_homepage_image_studio_entry_preserves_a_non_generating_professional_handoff():
    parser = _LinkParser()
    page = read("public/ask-crump.html")
    parser.feed(page)

    assert len(parser.links) == 1
    link = parser.links[0]
    destination = urlsplit(link["href"])
    assert destination.path == "/app"
    assert parse_qs(destination.query) == {
        "signup": ["1"],
        "source": ["image"],
        "plan": ["professional"],
        "intent": ["image"],
    }
    assert link["data-plan"] == "professional"
    assert "Opening the studio does not generate an image or use credits" in page
    assert "generation begins only after you review and confirm the request" in page


def test_image_is_a_navigation_handoff_not_a_server_attribution_intent():
    landing = read("public/landing.js")
    analytics = read("backend/product_analytics.py")

    assert "'document', 'presentation', 'resume', 'video', 'projects'" in landing
    assert ATTRIBUTION_INTENTS == frozenset({
        "document", "presentation", "resume", "video", "projects",
    })
    assert '"image"' not in analytics[
        analytics.index("ATTRIBUTION_INTENTS =") : analytics.index("ATTRIBUTION_CAMPAIGNS =")
    ]
    assert "destination.searchParams.get('intent')" in landing
    assert "intent: creationIntent" in landing
    assert normalize_attribution(
        acquisition="direct",
        placement=None,
        campaign=None,
        creative=None,
        intent="image",
    ) == {
        "acquisition": "direct",
        "placement": None,
        "campaign": None,
        "creative": None,
        "intent": None,
    }
