from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


@dataclass
class HtmlNode:
    tag: str
    attrs: dict[str, str]
    parent: "HtmlNode | None" = None
    children: list["HtmlNode"] = field(default_factory=list)

    @property
    def classes(self) -> set[str]:
        return set(self.attrs.get("class", "").split())


class AppDomParser(HTMLParser):
    VOID_TAGS = {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }

    def __init__(self) -> None:
        super().__init__()
        self.root = HtmlNode("document", {})
        self.stack = [self.root]
        self.by_id: dict[str, HtmlNode] = {}

    def handle_starttag(self, tag: str, attrs) -> None:
        attributes = {str(key): str(value or "") for key, value in attrs}
        parent = self.stack[-1]
        node = HtmlNode(tag.lower(), attributes, parent)
        parent.children.append(node)
        if attributes.get("id"):
            self.by_id[attributes["id"]] = node
        if tag.lower() not in self.VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(self, tag: str, attrs) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() not in self.VOID_TAGS:
            self.stack.pop()

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.lower()
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == normalized:
                del self.stack[index:]
                return


def css_blocks(css: str, selector: str) -> list[str]:
    return re.findall(rf"{re.escape(selector)}\s*\{{([^{{}}]*)\}}", css, re.DOTALL)


def declarations_contain(blocks: list[str], *needles: str) -> bool:
    normalized = [re.sub(r"\s+", " ", block).strip() for block in blocks]
    return any(all(needle in block for needle in needles) for block in normalized)


def hex_luminance(color: str) -> float:
    values = [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    channels = [
        value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
        for value in values
    ]
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast_ratio(foreground: str, background: str) -> float:
    foreground_luminance = hex_luminance(foreground)
    background_luminance = hex_luminance(background)
    high = max(foreground_luminance, background_luminance)
    low = min(foreground_luminance, background_luminance)
    return (high + 0.05) / (low + 0.05)


def custom_properties(block: str) -> dict[str, str]:
    return {
        name: value.lower()
        for name, value in re.findall(r"(--[\w-]+)\s*:\s*(#[0-9a-fA-F]{6})\s*;", block)
    }


def test_attachment_preview_is_a_real_accessible_composer_row() -> None:
    app = read("public/app.html")
    javascript = read("public/crump-5.0.js")
    styles = read("public/crump-design-pass.css")
    parser = AppDomParser()
    parser.feed(app)

    preview = parser.by_id["filePreview"]
    assert preview.parent is not None
    assert "v1-command-dock" in preview.parent.classes
    assert preview.attrs["role"] == "region"
    assert preview.attrs["aria-label"] == "Attachments ready to send"

    composer_children = preview.parent.children
    preview_index = composer_children.index(preview)
    input_area = next(node for node in composer_children if "input-area" in node.classes)
    assert preview_index < composer_children.index(input_area)

    dock_blocks = css_blocks(styles, "body.crump-v1-body .v1-command-dock")
    tray_blocks = css_blocks(
        styles,
        "body.crump-v1-body #filePreview.crump50-attachment-tray",
    )
    remove_blocks = css_blocks(styles, "body.crump-v1-body .crump50-upload-remove")
    assert declarations_contain(dock_blocks, "align-content: end", "row-gap: 8px")
    assert declarations_contain(
        tray_blocks,
        "position: relative !important",
        "inset: auto !important",
        "justify-self: center",
        "overflow-x: auto",
    )
    assert "body.crump-v1-body #filePreview.crump50-attachment-tray:empty { display: none !important; }" in styles
    assert declarations_contain(remove_blocks, "width: 36px !important", "height: 36px !important")

    mobile_start = styles.index("@media (max-width:680px)")
    mobile_end = styles.find("@media ", mobile_start + 1)
    mobile_css = styles[mobile_start : mobile_end if mobile_end >= 0 else len(styles)]
    assert "#filePreview.crump50-attachment-tray" in mobile_css
    assert "width: 100% !important" in mobile_css
    assert ".crump50-upload-remove" in mobile_css
    assert "width: 40px !important" in mobile_css
    assert "height: 40px !important" in mobile_css

    assert "document.body.classList.toggle('crump50-has-attachments'" in javascript
    assert "body.crump-v1-body.crump50-has-attachments #scrollToEndBtn" in styles
    assert "removeAttachment(item.localId, {restoreFocus: true})" in javascript
    assert "name.title = item.name;" in javascript
    assert "const next = remaining[Math.min(index" in javascript
    assert "next?.focus?.();" in javascript


def test_response_utilities_use_readable_semantic_colors_in_both_themes() -> None:
    styles = read("public/crump-design-pass.css")

    root_match = re.search(r":root\s*\{(.*?)\n\}", styles, re.DOTALL)
    dark_match = re.search(r'html\[data-theme="dark"\]\s*\{(.*?)\n\}', styles, re.DOTALL)
    assert root_match and dark_match

    light_tokens = custom_properties(root_match.group(1))
    dark_tokens = custom_properties(dark_match.group(1))
    semantic_tokens = {
        "--atelier-panel-text",
        "--atelier-panel-text-2",
        "--atelier-panel-muted",
        "--atelier-panel-label",
        "--atelier-panel-danger",
    }
    for name in semantic_tokens:
        assert contrast_ratio(light_tokens[name], light_tokens["--atelier-paper"]) >= 4.5, name
        assert contrast_ratio(dark_tokens[name], dark_tokens["--atelier-paper"]) >= 4.5, name

    response_selectors = {
        ".message-intelligence-receipt",
        ".message-intelligence-label",
        ".message-intelligence-signal",
        ".message-action-btn",
        ".outcome-feedback",
        ".outcome-continuity",
        ".outcome-continuity-prompt",
        ".outcome-continuity-detail",
        ".outcome-feedback-prompt",
        ".outcome-referral-prompt",
        ".outcome-feedback-btn",
        ".outcome-project-btn",
        ".outcome-feedback-status",
        ".crump50-artifact",
        ".crump50-artifact-copy strong",
        ".crump50-artifact-copy small",
        ".crump50-artifact-actions button",
    }
    for selector in response_selectors:
        assert selector in styles, f"Missing final-theme coverage for {selector}"

    actions_rule = re.search(
        r"body\.crump-v1-body \.message-actions,.*?\{([^{}]+)\}",
        styles,
        re.DOTALL,
    )
    assert actions_rule and "opacity: 1 !important" in actions_rule.group(1)

    light_project = css_blocks(styles, "body.crump-v1-body .outcome-project-btn")
    dark_project = css_blocks(
        styles,
        'html[data-theme="dark"] body.crump-v1-body .outcome-project-btn',
    )
    assert declarations_contain(light_project, "background: var(--atelier-ink) !important", "color: #fffdf9 !important")
    assert declarations_contain(dark_project, "background: #e7deca !important", "color: #15171a !important")

    keepsake_badge = css_blocks(
        styles,
        "body.crump-v1-body .crump50-artifact.cv-keepsake-real::before",
    )
    assert declarations_contain(keepsake_badge, "grid-column: 1 / -1")
    assert 'html[data-theme="dark"] body.crump-v1-body .outcome-continuity' in styles
    assert 'html[data-theme="dark"] body.crump-v1-body .crump50-artifact' in styles
    assert 'html[data-theme="dark"] body.crump-v1-body .message-action-btn' in styles


def test_release_quality_contract_covers_the_exact_reported_mobile_surfaces() -> None:
    styles = read("public/crump-design-pass.css")
    ui = read("public/ui-functions.js")

    for copy in (
        "Continue this work later",
        "Keep this conversation in a private Project.",
        "Did this move your work forward?",
        "Yes",
        "Not yet",
    ):
        assert copy in ui

    for selector in (
        ".outcome-continuity-detail",
        ".outcome-feedback-prompt",
        ".outcome-feedback-btn",
        ".outcome-project-btn",
        ".message-action-btn",
    ):
        assert selector in styles

    assert "body.crump-v1-body .outcome-feedback-btn {" in styles
    assert "color: var(--atelier-panel-text-2) !important" in styles
    assert "body.crump-v1-body .message-action-btn {" in styles
    assert "color: var(--atelier-panel-muted) !important" in styles


def test_light_theme_release_audit_covers_every_lazy_product_surface() -> None:
    styles = read("public/crump-design-pass.css")

    # These product sheets are injected after the main design pass. Their
    # overrides must remain both light-theme scoped and important so old dark
    # defaults cannot wash out text on the paper canvas.
    audited_selectors = (
        ".v1-auth-card .auth-header h1",
        ".v1-registration-pending h2",
        ".v1-auth-card .form-input::placeholder",
        ".crump50-file-viewer-placeholder",
        ".crump50-reference-result",
        ".crump52-file-attachment",
        ".crump53-video-engine-card",
        ".crump53-video-engine-guide span",
        ".crump53-video-reference-role select",
        ".crump53-library-document span",
        ".crump531-file-row",
        ".crump57-library-toolbar input",
        ".crump57-book-author",
        ".v1-settings-sheet .v1-kicker",
        ".settings-chevron",
        ".crump44-advanced-chevron",
        ".crump44-memory-empty",
        ".billing51-balance-card > div:first-child > strong small",
        ".billing51-allowance > div:first-child span",
        ".billing51-history-row",
        ".message-status.failed",
    )
    for selector in audited_selectors:
        assert selector in styles, f"Missing final light-theme coverage for {selector}"

    audit_start = styles.index("Release audit: complete light-surface contrast boundaries")
    audit_css = styles[audit_start:]
    assert 'html[data-theme="light"]' in audit_css
    assert audit_css.count("!important") >= 45
    assert "html[data-theme=\"light\"] body.crump-v1-body *" not in audit_css

    # Nested media viewers, covers, Terms, and onboarding are intentional dark
    # islands and require explicit light copy rather than a global recolor.
    for selector in (
        ".crump50-file-viewer-placeholder",
        ".crump53-video-project-context strong",
        ".crump57-cover-placeholder strong",
        ":is(.v1-terms-card,.v1-onboarding-card)",
    ):
        assert selector in audit_css
    assert "color: #f1eee7 !important" in audit_css
    assert "color: #f4f1e9 !important" in audit_css
