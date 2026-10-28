from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "tests" / "fixtures" / "indexable-pages.json"
SITEMAP_PATH = ROOT / "public" / "sitemap.xml"
LD_JSON_PATTERN = re.compile(
    r'<script\s+type="application/ld\+json">\s*(.*?)\s*</script>',
    re.DOTALL,
)
CANONICAL_PATTERN = re.compile(r'<link\s+rel="canonical"\s+href="([^"]+)">')
ROBOTS_PATTERN = re.compile(r'<meta\s+name="robots"\s+content="([^"]+)">')
ARTICLE_MODIFIED_PATTERN = re.compile(
    r'<meta\s+property="article:modified_time"\s+content="([^"]+)">'
)
VISIBLE_REVIEWED_PATTERN = re.compile(r"Reviewed <strong>([^<]+)</strong>")
GUIDE_URLS = {
    "https://www.askcrump.com/guides/audit-ai-resume-bullets",
    "https://www.askcrump.com/guides/editable-ai-powerpoint-review",
    "https://www.askcrump.com/guides/rough-idea-six-week-launch-plan",
    "https://www.askcrump.com/guides/what-ai-project-should-remember",
    "https://www.askcrump.com/guides/word-or-pdf-ai-document-output",
}


def load_manifest_pages() -> list[dict[str, str]]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert manifest["schemaVersion"] == 1
    pages = manifest["pages"]
    assert pages
    return pages


def article_json_ld(page: str) -> dict[str, object]:
    blocks = [json.loads(match) for match in LD_JSON_PATTERN.findall(page)]
    articles = [block for block in blocks if isinstance(block, dict) and block.get("@type") == "Article"]
    assert len(articles) == 1
    return articles[0]


def test_indexable_page_manifest_exactly_matches_sitemap_and_source_metadata():
    pages = load_manifest_pages()
    urls = [page["url"] for page in pages]
    sources = [page["source"] for page in pages]
    assert len(urls) == len(set(urls))
    assert len(sources) == len(set(sources))
    assert {page["kind"] for page in pages} <= {"page", "guide"}
    assert {page["url"] for page in pages if page["kind"] == "guide"} == GUIDE_URLS

    expected_sitemap: dict[str, str] = {}
    for item in pages:
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", item["lastmod"])
        date.fromisoformat(item["lastmod"])
        source = ROOT / item["source"]
        assert source.is_file()
        page = source.read_text(encoding="utf-8")
        assert CANONICAL_PATTERN.findall(page) == [item["url"]]
        robots = ROBOTS_PATTERN.findall(page)
        assert len(robots) == 1
        directives = {directive.strip().lower() for directive in robots[0].split(",")}
        assert {"index", "follow"} <= directives
        assert "noindex" not in directives
        assert "nofollow" not in directives
        expected_sitemap[item["url"]] = item["lastmod"]

    namespace = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    root = ET.fromstring(SITEMAP_PATH.read_text(encoding="utf-8"))
    entries = [
        (
            entry.findtext("sm:loc", namespaces=namespace),
            entry.findtext("sm:lastmod", namespaces=namespace),
        )
        for entry in root.findall("sm:url", namespace)
    ]
    assert len(entries) == len({url for url, _ in entries})
    assert dict(entries) == expected_sitemap


def test_guide_review_dates_agree_with_sitemap_article_metadata_and_visible_copy():
    for item in load_manifest_pages():
        if item["kind"] != "guide":
            continue

        page = (ROOT / item["source"]).read_text(encoding="utf-8")
        lastmod = item["lastmod"]
        assert ARTICLE_MODIFIED_PATTERN.findall(page) == [lastmod]
        assert article_json_ld(page)["dateModified"] == lastmod

        reviewed = date.fromisoformat(lastmod)
        visible_reviewed = f"{reviewed.strftime('%B')} {reviewed.day}, {reviewed.year}"
        assert VISIBLE_REVIEWED_PATTERN.findall(page) == [visible_reviewed]
