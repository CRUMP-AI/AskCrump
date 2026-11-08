from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def string_array(source: str, name: str) -> list[str]:
    match = re.search(rf"var {re.escape(name)} = \[([^\]]*)\];", source)
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
        "home",
        "chats",
        "projects",
        "library",
        "studios",
        "you",
    ]
    assert string_array(shell, "MOBILE_ORDER") == [
        "home",
        "chats",
        "projects",
        "library",
        "studios",
    ]
    assert string_array(shell, "MORE_DESTINATIONS") == []
    assert 'button.id = \'cvMobileYou\'' in shell
    assert "'browser'" not in string_array(shell, "ORDER")


def test_chats_drawer_is_keyboard_accessible_and_restores_focus() -> None:
    shell = read("public/crump-vision-shell-1.0.js")

    assert "? ' data-cv-drawer-toggle aria-controls=\"sidebar\" aria-expanded=\"false\"'" in shell
    assert "if (event.key !== 'Escape' || !conversationDrawerIsOpen()) return;" in shell
    assert "closeConversationDrawer(true, true);" in shell
    assert "conversationDrawerOpener = opener || document.activeElement;" in shell
    assert "opener.focus({ preventScroll: true });" in shell
    assert "target.focus({ preventScroll: true });" in shell
    assert "button.setAttribute('aria-expanded', expanded ? 'true' : 'false');" in shell
    toggle = shell[shell.index("function toggleConversationDrawer(opener)") : shell.index("function startNewConversation()")]
    assert "track('chats');" in toggle
    assert "toggleConversationLibrary?.({ recordSelection: false })" in shell


def test_public_names_keep_legacy_owners_and_analytics_compatible() -> None:
    shell = read("public/crump-vision-shell-1.0.js")

    assert string_object(shell, "NEW_TO_OLD") == {
        "home": "ask",
        "projects": "projects",
        "library": "library",
        "studios": "video",
        "you": "you",
        "files": "projects",
        "autonomous": "code",
    }
    assert string_object(shell, "ANALYTICS_SOURCE") == {
        "home": "ask",
        "chats": "chats",
        "projects": "projects",
        "files": "projects",
        "library": "library",
        "studios": "video",
        "autonomous": "code",
        "you": "you",
    }
    assert "window.CrumpProduct53.openFiles();" in shell
    assert "window.CrumpProductLoader.openFiles();" in shell
    assert "legacy.open(oldId, silent ? { recordSelection: false, focus: false } : undefined);" in shell
    assert "if (id === 'browser') return;" in shell
    assert "[data-v1-settings-tab=\"profile\"]" in shell


def test_compact_shell_has_one_chats_control() -> None:
    styles = read("public/crump-vision-shell-1.0.css")

    assert 'body.crump-v1-body #menuBtn' in styles
    assert 'display: none !important;' in styles[
        styles.index('body.crump-v1-body #menuBtn') : styles.index('body.crump-v1-body #menuBtn') + 180
    ]


def test_files_destination_only_stays_active_while_its_surface_is_visible() -> None:
    shell = read("public/crump-vision-shell-1.0.js")

    assert "productStudio && !productStudio.hidden" in shell
    assert "productSheet && productSheet.dataset.projectView === 'files'" in shell
    assert "var filesOwnSurface = filesSurfaceIsOpen()" in shell
    assert "currentId === 'files' && filesNavigationIsPending()" in shell
    assert "var mapped = filesOwnSurface ? 'files'" in shell
    assert "document.addEventListener('crump:product-view-changed'" in shell


def test_authoritative_home_and_account_views_cannot_be_replaced() -> None:
    shell = read("public/crump-vision-shell-1.0.js")

    assert "sourceKey === 'ask' || sourceKey === 'home' || sourceKey === 'profile' || sourceKey === 'you'" in shell
    assert "return false;" in shell[
        shell.index("sourceKey === 'ask'") : shell.index("var key = normalizeId(sourceKey)")
    ]
    assert "create: 'home'" in shell
    assert "studios: 'video'" in shell
    assert "you: 'you'" in shell
    assert "browser: 'browser'" in shell


def test_projects_use_real_api_data_without_a_local_next_steps_store() -> None:
    projects = read("public/crump-vision-projects-1.0.js")

    assert "localStorage" not in projects
    assert "Next Steps" not in projects
    assert "api('/api/projects', authBoundary)" in projects
    assert "api('/api/projects/' + encodeURIComponent(project.id), authBoundary)" in projects
    assert "api('/api/projects/' + encodeURIComponent(project.id) + '/chats', authBoundary)" in projects
    assert "api('/api/library/books', authBoundary)" in projects
    assert "new URL(window.location.href).searchParams.get('project')" in projects
    assert 'role="tablist" aria-label="Your projects"' in projects
    assert 'role="tab"' in projects
    assert "event.key !== 'ArrowLeft' && event.key !== 'ArrowRight'" in projects
    assert "detail.setAttribute('role', 'tabpanel')" in projects
    assert "detail.dataset.cvpActiveProject = selectionId" in projects
    assert "detail.dataset.cvpActiveProject !== selectionId" in projects


def test_primary_projects_view_restores_the_owned_conversation_resume_contract() -> None:
    projects = read("public/crump-vision-projects-1.0.js")

    assert 'data-cvp-chat="' in projects
    assert 'aria-label="Continue “' in projects
    assert "await window.syncChatsFromServer()" in projects
    assert "if (!localConversation(chatId))" in projects
    assert "await Promise.resolve(window.loadChat(chatId))" in projects
    assert "String(window.currentChatId || '').trim() !== chatId" in projects
    assert "resumeActionIsCurrent(button, projectId, authBoundary)" in projects
    assert "captureProjectsAuthBoundary()" in projects
    assert "projectsViewIsCurrent(detail.closest('.cvp-root'), authBoundary)" in projects
    assert "boundary.register('vision-projects', scrubProjectsPrivateView)" in projects
    assert "button.dataset.cvpOpening === 'true'" in projects
    assert "openAsk()" in projects
    assert "track('RecentWorkResumed'" in projects
    assert "eventKey: 'recent-work-resumed'" in projects
    assert "source: 'project'" in projects
    assert projects.index("window.loadChat(chatId)") < projects.index("if (!openAsk())")
    assert projects.index("if (!openAsk())") < projects.index("recordProjectResume();")


def test_first_screen_has_six_clear_jumps_without_a_second_destination_map() -> None:
    app = read("public/app.html")

    assert "<h1>What can I help you get done?</h1>" in app
    assert '<p class="v1-launchpad-actions-label">Ways to begin</p>' in app
    assert app.count('class="v1-launch-card') == 6
    assert app.count('data-home-document-entry') == 1
    for command in ("projects", "browser", "file", "image", "video"):
        assert app.count(f'data-v1-command="{command}"') == 1
    assert 'data-v1-command="focus"' not in app
    assert 'class="v1-launchpad-foot"' not in app

