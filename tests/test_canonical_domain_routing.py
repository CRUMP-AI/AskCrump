import json
from pathlib import Path
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]


def read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_internal_landing_slugs_permanently_redirect_to_canonical_domains():
    config = json.loads(read("vercel.json"))
    redirects = config["redirects"]

    global_redirects = {
        rule["source"]: rule
        for rule in redirects
        if not rule.get("has")
    }
    assert global_redirects["/ask-crump"] == {
        "source": "/ask-crump",
        "destination": "https://www.askcrump.com/",
        "permanent": True,
    }
    assert global_redirects["/clever-crump"] == {
        "source": "/clever-crump",
        "destination": "https://www.clevercrump.com/",
        "permanent": True,
    }


def test_clever_crump_does_not_serve_duplicate_ask_product_pages():
    config = json.loads(read("vercel.json"))
    clever_redirects = {
        rule["source"]: rule
        for rule in config["redirects"]
        if rule.get("has") == [{"type": "host", "value": "www.clevercrump.com"}]
    }
    destinations = {
        "/app": "https://www.askcrump.com/app",
        "/ai-presentation-maker": "https://www.askcrump.com/ai-presentation-maker",
        "/ai-document-generator": "https://www.askcrump.com/ai-document-generator",
        "/ai-resume-builder": "https://www.askcrump.com/ai-resume-builder",
        "/ai-video-generator": "https://www.askcrump.com/ai-video-generator",
        "/legal": "https://www.askcrump.com/legal",
        "/delete-account": "https://www.askcrump.com/delete-account",
    }

    assert set(clever_redirects) == set(destinations)
    for source, destination in destinations.items():
        assert clever_redirects[source]["destination"] == destination
        assert clever_redirects[source]["permanent"] is True


def test_clever_crump_has_host_correct_search_discovery_files():
    config = json.loads(read("vercel.json"))
    discovery_rewrites = {
        rule["source"]: rule["destination"]
        for rule in config["rewrites"]
        if rule.get("has") == [{"type": "host", "value": "www.clevercrump.com"}]
        and rule["source"] in {"/robots.txt", "/sitemap.xml"}
    }
    assert discovery_rewrites == {
        "/robots.txt": "/clever-crump-robots.txt",
        "/sitemap.xml": "/clever-crump-sitemap.xml",
    }

    robots = read("public/clever-crump-robots.txt")
    assert "Sitemap: https://www.clevercrump.com/sitemap.xml" in robots
    assert "https://www.askcrump.com/sitemap.xml" not in robots
    assert "Disallow: /delete-account" in robots

    sitemap = read("public/clever-crump-sitemap.xml")
    parsed = ET.fromstring(sitemap)
    namespace = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    urls = parsed.findall("sm:url", namespace)
    assert len(urls) == 1
    assert urls[0].findtext("sm:loc", namespaces=namespace) == "https://www.clevercrump.com/"
    assert urls[0].findtext("sm:lastmod", namespaces=namespace) == "2026-08-29"


def test_ask_crump_robots_uses_the_clean_account_deletion_path():
    robots = read("public/robots.txt")

    assert "Sitemap: https://www.askcrump.com/sitemap.xml" in robots
    assert "Disallow: /delete-account" in robots
    assert "Disallow: /delete-account.html" not in robots
