from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def string_array(source: str, name: str) -> list[str]:
    match = re.search(rf"var {re.escape(name)} = \[([^\]]+)\];", source)
    assert match, f"missing {name}"
    return re.findall(r"'([^']+)'", match.group(1))


def string_object(source: str, name: str) -> dict[str, str]:
    match = re.search(
        rf"var {re.escape(name)} = \{{(.*?)\n\s*\}};",
        source,
        flags=re.DOTALL,
    )
    assert match, f"missing {name}"
    return dict(re.findall(r"([a-z]+):\s*'([^']+)'", match.group(1)))


def test_shell_exposes_one_exact_desktop_and_mobile_information_architecture() -> None:
    shell = read("public/crump-vision-shell-1.0.js")

    assert string_array(shell, "ORDER") == [
        "ask",
        "projects",
        "files",
        "library",
        "video",
        "autonomous",
    ]
    assert string_array(shell, "MOBILE_ORDER") == [
        "ask",
        "projects",
        "library",
        "video",
        "more",
    ]
    assert string_array(shell, "MORE_DESTINATIONS") == [
        "files",
        "autonomous",
        "profile",
    ]
    assert 'class="cv-rail-utility cv-profile-link" data-cv-destination="profile"' in shell
    assert "var beta = id === 'autonomous' ? '<small>Beta</small>' : '';" in shell


def test_more_sheet_is_keyboard_accessible_and_restores_focus() -> None:
    shell = read("public/crump-vision-shell-1.0.js")

    assert 'aria-haspopup="dialog" aria-controls="cvMoreMenu" aria-expanded="false"' in shell
    assert 'role="dialog" aria-modal="true" aria-labelledby="cvMoreTitle"' in shell
    assert "if (event.key === 'Escape')" in shell
    assert "if (event.key !== 'Tab') return;" in shell
    assert "if (event.shiftKey && document.activeElement === first)" in shell
    assert "else if (!event.shiftKey && document.activeElement === last)" in shell
    assert "moreMenuOpener.focus({ preventScroll: true });" in shell
    assert "button.setAttribute('aria-expanded', 'true');" in shell
    assert "button.setAttribute('aria-expanded', 'false');" in shell
    assert 'class="cv-more-backdrop" data-cv-more-close tabindex="-1"' in shell


def test_public_names_keep_legacy_owners_and_analytics_compatible() -> None:
    shell = read("public/crump-vision-shell-1.0.js")

    assert string_object(shell, "NEW_TO_OLD") == {
        "ask": "ask",
        "projects": "projects",
        "library": "library",
        "video": "video",
        "autonomous": "code",
        "profile": "you",
    }
    assert string_object(shell, "ANALYTICS_SOURCE") == {
        "ask": "ask",
        "projects": "projects",
        "files": "projects",
        "library": "library",
        "video": "video",
        "autonomous": "code",
        "profile": "you",
    }
    assert "window.CrumpProduct53.openFiles();" in shell
    assert "window.CrumpProductLoader.openFiles();" in shell
    assert "legacy.open(oldId);" in shell
    assert "[data-v1-settings-tab=\"profile\"]" in shell


def test_files_destination_only_stays_active_while_its_surface_is_visible() -> None:
    shell = read("public/crump-vision-shell-1.0.js")

    assert "productStudio && !productStudio.hidden" in shell
    assert "productSheet && productSheet.dataset.projectView === 'files'" in shell
    assert "var filesOwnSurface = filesSurfaceIsOpen()" in shell
    assert "currentId === 'files' && filesNavigationIsPending()" in shell
    assert "var mapped = filesOwnSurface ? 'files'" in shell
    assert "document.addEventListener('crump:product-view-changed'" in shell


def test_presentation_only_views_cannot_replace_real_product_owners() -> None:
    shell = read("public/crump-vision-shell-1.0.js")

    assert "sourceKey === 'home' || sourceKey === 'studios' || sourceKey === 'you'" in shell
    assert "return false;" in shell[
        shell.index("sourceKey === 'home'") : shell.index("var key = normalizeId(sourceKey)")
    ]
    assert "create: 'ask'" in shell
    assert "studios: 'video'" in shell
    assert "you: 'profile'" in shell


def test_projects_use_real_api_data_without_a_local_next_steps_store() -> None:
    projects = read("public/crump-vision-projects-1.0.js")

    assert "localStorage" not in projects
    assert "Next Steps" not in projects
    assert "api('/api/projects')" in projects
    assert "api('/api/projects/' + encodeURIComponent(project.id))" in projects
    assert "api('/api/projects/' + encodeURIComponent(project.id) + '/chats')" in projects
    assert "api('/api/library/books')" in projects
    assert "new URL(window.location.href).searchParams.get('project')" in projects
    assert 'role="tablist" aria-label="Your projects"' in projects
    assert 'role="tab"' in projects
    assert "event.key !== 'ArrowLeft' && event.key !== 'ArrowRight'" in projects
    assert "detail.setAttribute('role', 'tabpanel')" in projects
    assert "detail.dataset.cvpActiveProject = selectionId" in projects
    assert "detail.dataset.cvpActiveProject !== selectionId" in projects


def test_first_screen_has_four_clear_jumps_without_a_second_destination_map() -> None:
    app = read("public/app.html")

    assert "<h1>What can I help you get done?</h1>" in app
    assert '<p class="v1-launchpad-actions-label">Ways to begin</p>' in app
    assert app.count('class="v1-launch-card') == 4
    for command in ("projects", "file", "image", "video"):
        assert app.count(f'data-v1-command="{command}"') == 1
    assert 'data-v1-command="focus"' not in app
    assert 'class="v1-launchpad-foot"' not in app

