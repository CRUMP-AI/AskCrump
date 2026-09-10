from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
PUBLIC_HTML = sorted([*PUBLIC.glob("*.html"), *PUBLIC.glob("guides/*.html")])
FIRST_PARTY_HOSTS = {
    "",
    "askcrump.com",
    "www.askcrump.com",
    "clevercrump.com",
    "www.clevercrump.com",
}
PLATFORM_RUNTIME_PATHS = {
    "/_vercel/insights/script.js",
    "/_vercel/speed-insights/script.js",
}
RESOURCE_ATTRIBUTES = {
    "a": ("href",),
    "img": ("src",),
    "link": ("href",),
    "script": ("src",),
    "source": ("src", "srcset"),
    "video": ("poster", "src"),
}


class PublicReferenceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.references: list[tuple[str, str, str]] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        attributes = {str(key).lower(): str(value or "") for key, value in attrs}
        element_id = attributes.get("id") or attributes.get("name")
        if element_id:
            self.ids.add(element_id)
        for attribute in RESOURCE_ATTRIBUTES.get(tag.lower(), ()):
            value = attributes.get(attribute, "").strip()
            if not value:
                continue
            if attribute == "srcset":
                for candidate in value.split(","):
                    url = candidate.strip().split()[0]
                    if url:
                        self.references.append((tag.lower(), attribute, url))
                continue
            self.references.append((tag.lower(), attribute, value))


def _parse(path: Path) -> PublicReferenceParser:
    parser = PublicReferenceParser()
    parser.feed(path.read_text(encoding="utf-8"))
    return parser


def _public_target(path: str, source: Path) -> Path | None:
    decoded = unquote(path or "")
    if not decoded:
        return source
    if decoded == "/":
        return PUBLIC / "ask-crump.html"
    if decoded.startswith("/api/"):
        return None

    clean = decoded.rstrip("/") or "/"
    route_map = {
        "/app": "app.html",
        "/ask-crump": "ask-crump.html",
        "/clever-crump": "clever-crump.html",
        "/legal": "legal.html",
        "/delete-account": "delete-account.html",
    }
    if clean in route_map:
        return PUBLIC / route_map[clean]
    if clean.startswith("/guides/") and "." not in Path(clean).name:
        return (PUBLIC / clean.removeprefix("/")).with_suffix(".html")
    if clean.startswith("/ai-") and "." not in Path(clean).name:
        return (PUBLIC / clean.removeprefix("/")).with_suffix(".html")
    return PUBLIC / clean.removeprefix("/")


def test_every_static_first_party_link_and_asset_resolves() -> None:
    parsed = {path: _parse(path) for path in PUBLIC_HTML}
    broken: list[str] = []

    for source, document in parsed.items():
        for tag, attribute, raw_url in document.references:
            if raw_url.startswith(("#", "data:", "javascript:", "blob:")):
                continue
            destination = urlsplit(raw_url)
            if destination.scheme in {"mailto", "tel"}:
                continue
            if destination.scheme and destination.scheme not in {"http", "https"}:
                broken.append(f"{source.relative_to(ROOT)}::{raw_url} uses an unsupported scheme")
                continue
            if destination.netloc.lower() not in FIRST_PARTY_HOSTS:
                continue
            if destination.path in PLATFORM_RUNTIME_PATHS:
                continue

            if destination.path in {"", "/"}:
                target = PUBLIC / (
                    "clever-crump.html"
                    if "clevercrump.com" in destination.netloc.lower()
                    else "ask-crump.html"
                )
            else:
                target = _public_target(destination.path, source)
            if target is None:
                continue
            if not target.is_file():
                broken.append(
                    f"{source.relative_to(ROOT)}::{tag}[{attribute}]={raw_url} -> "
                    f"{target.relative_to(ROOT)}"
                )
                continue
            if destination.fragment and target.suffix.lower() == ".html":
                target_parser = parsed.get(target) or _parse(target)
                if destination.fragment not in target_parser.ids:
                    broken.append(
                        f"{source.relative_to(ROOT)}::{raw_url} -> missing "
                        f"#{destination.fragment} in {target.relative_to(ROOT)}"
                    )

    assert not broken, "Broken first-party public references:\n" + "\n".join(broken)


def test_public_reference_inventory_is_reviewed() -> None:
    references = [
        (path.relative_to(ROOT).as_posix(), *reference)
        for path in PUBLIC_HTML
        for reference in _parse(path).references
    ]

    assert len(PUBLIC_HTML) == 15
    assert len(references) == 447
