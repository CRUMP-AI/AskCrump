from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
from pathlib import Path
import shutil
import sys

PACKAGE_ROOT = Path(__file__).resolve().parent

EXPECTED_BASELINE_BLOBS = {
    Path('public/crump-v1-body.js'): '75386a3660b935a38e0c79583383605a0be7af8d',
    Path('public/crump-v1-body.css'): '57e7bcc53d7de6ddf14834877ef02dccc9ca8a68',
    Path('public/app.js'): '9e55db2983a64829b3db61841da6bf326926633d',
    Path('public/crump-billing-5.1.js'): '037820a20fd963abaed0e32a11b2bba91c3a1162',
    Path('public/crump-billing-5.1.css'): '47ab14b57f761a785aed619b7dd4ed400b18ceff',
}


def normalized_git_blob_sha(path: Path) -> str:
    text = path.read_text(encoding='utf-8')
    data = text.replace('\r\n', '\n').replace('\r', '\n').encode('utf-8')
    header = f'blob {len(data)}\0'.encode('ascii')
    return hashlib.sha1(header + data).hexdigest()


def replace_exact(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(
            f'{label}: expected exactly one audited match, found {count}. '
            'Your local file has diverged; review PATCHES/sidebar-navigation-cleanup.diff and merge manually.'
        )
    return text.replace(old, new, 1)


def append_once(text: str, marker: str, block: str, label: str) -> str:
    if marker in text:
        raise RuntimeError(
            f'{label}: cleanup marker already exists. This change may already be applied.'
        )
    return text.rstrip() + '\n\n' + block.strip() + '\n'


def patch_app_html(text: str) -> str:
    desktop_duplicates = '''      <div class="v1-rail-spacer"></div>

      <div class="v1-rail-stack">
        <button type="button" class="v1-rail-button" data-v1-command="settings" aria-label="Settings" title="Settings">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z"/><path d="M19.4 15a1.8 1.8 0 0 0 .36 2l.05.05-2.76 2.76-.05-.05a1.8 1.8 0 0 0-2-.36 1.8 1.8 0 0 0-1.1 1.65V21h-3.8v-.07A1.8 1.8 0 0 0 9 19.3a1.8 1.8 0 0 0-2 .36l-.05.05-2.76-2.76.05-.05a1.8 1.8 0 0 0 .36-2A1.8 1.8 0 0 0 2.95 13H3v-3.8h-.05A1.8 1.8 0 0 0 4.6 8.1a1.8 1.8 0 0 0-.36-2l-.05-.05L6.95 3.3l.05.05a1.8 1.8 0 0 0 2 .36A1.8 1.8 0 0 0 10.1 2.05V2h3.8v.05A1.8 1.8 0 0 0 15 3.7a1.8 1.8 0 0 0 2-.36l.05-.05 2.76 2.76-.05.05a1.8 1.8 0 0 0-.36 2 1.8 1.8 0 0 0 1.65 1.1H21V13h-.05A1.8 1.8 0 0 0 19.4 15Z"/></svg>
        </button>
        <button type="button" class="v1-rail-button" data-v1-command="billing" aria-label="Plan and credits" title="Plan & credits">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 7.5h14v9H5z"/><path d="M8 4.5v3M16 4.5v3M8 16.5v3M16 16.5v3"/></svg>
        </button>
      </div>
'''
    text = replace_exact(
        text,
        desktop_duplicates,
        '',
        'public/app.html duplicate desktop Settings/Billing rail controls',
    )

    settings_row = '''        <button id="settingsBtn" class="sidebar-footer-btn" type="button">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z"/><path d="M19.4 15a1.8 1.8 0 0 0 .36 2l.05.05-2.76 2.76-.05-.05a1.8 1.8 0 0 0-2-.36"/></svg>
          <span>Settings</span>
        </button>'''
    settings_clean = '''        <button id="settingsBtn" class="sidebar-footer-btn" type="button">
          <span>Settings</span>
        </button>'''
    text = replace_exact(
        text,
        settings_row,
        settings_clean,
        'public/app.html Settings footer icon cleanup',
    )

    billing_row = '''        <button id="upgradeBtnSidebar" class="sidebar-footer-btn" type="button">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 7.5h14v9H5z"/><path d="M8 4.5v3M16 4.5v3"/></svg>
          <span>Plan & credits</span>
        </button>'''
    billing_clean = '''        <button id="upgradeBtnSidebar" class="sidebar-footer-btn" type="button">
          <span>Plan & credits</span>
        </button>'''
    text = replace_exact(
        text,
        billing_row,
        billing_clean,
        'public/app.html Plan & credits footer icon cleanup',
    )
    return text


def patch_body_js(text: str) -> str:
    stale_cases = """      case 'settings':
        forwardClick('settingsBtn');
        break;
      case 'billing':
        forwardClick('upgradeBtnSidebar');
        break;
"""
    return replace_exact(
        text,
        stale_cases,
        '',
        'public/crump-v1-body.js duplicate command handlers',
    )


def patch_body_css(text: str) -> str:
    text = replace_exact(
        text,
        'body.crump-v1-body .v1-rail-spacer { flex: 1; }\n',
        '',
        'public/crump-v1-body.css unused rail spacer',
    )
    block = '''/* =========================================================
   SIDEBAR NAVIGATION HARDENING — 2026-08-11
   Keep footer actions visually singular and prevent the live credit badge
   from wrapping into what looks like a separate navigation control.
   ========================================================= */
body.crump-v1-body .v1-library-footer {
  gap: 4px;
  padding: 12px 10px max(14px, env(safe-area-inset-bottom)) !important;
}

body.crump-v1-body .sidebar-footer-btn {
  display: flex !important;
  width: 100%;
  min-height: 48px !important;
  align-items: center;
  justify-content: flex-start;
  gap: 10px;
  padding: 0 12px !important;
}

body.crump-v1-body .sidebar-footer-btn > span {
  min-width: 0;
  text-align: left;
}

body.crump-v1-body .sidebar-footer-link svg {
  flex: 0 0 17px;
}'''
    return append_once(
        text,
        'SIDEBAR NAVIGATION HARDENING — 2026-08-11',
        block,
        'public/crump-v1-body.css navigation layout',
    )


def patch_app_js(text: str) -> str:
    return replace_exact(
        text,
        "        ['settingsBtn', () => window.openSettings?.()],\n",
        "        ['settingsBtn', () => {\n"
        "            document.getElementById('sidebar')?.classList.remove('active');\n"
        "            document.getElementById('sidebarOverlay')?.classList.remove('active');\n"
        "            window.openSettings?.();\n"
        "        }],\n",
        'public/app.js Settings mobile drawer cleanup',
    )


def patch_billing_js(text: str) -> str:
    return replace_exact(
        text,
        "    button.addEventListener('click', () => showBillingCenter());\n",
        "    button.addEventListener('click', () => {\n"
        "      $('#sidebar')?.classList.remove('active');\n"
        "      $('#sidebarOverlay')?.classList.remove('active');\n"
        "      showBillingCenter();\n"
        "    });\n",
        'public/crump-billing-5.1.js billing mobile drawer cleanup',
    )


def patch_billing_css(text: str) -> str:
    block = '''/* Sidebar navigation hardening — keep the live balance visually attached to
   the single Plan & credits row on narrow screens. */
body.crump-v1-body #upgradeBtnSidebar .billing51-sidebar-balance {
  display: inline-flex;
  flex: 0 0 auto;
  min-width: 42px;
  align-items: center;
  justify-content: center;
  margin-left: auto;
  white-space: nowrap;
  line-height: 1;
}'''
    return append_once(
        text,
        'Sidebar navigation hardening — keep the live balance',
        block,
        'public/crump-billing-5.1.css credit badge alignment',
    )


PATCHERS = {
    Path('public/app.html'): patch_app_html,
    Path('public/crump-v1-body.js'): patch_body_js,
    Path('public/crump-v1-body.css'): patch_body_css,
    Path('public/app.js'): patch_app_js,
    Path('public/crump-billing-5.1.js'): patch_billing_js,
    Path('public/crump-billing-5.1.css'): patch_billing_css,
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Apply the Ask Crump mobile/sidebar navigation cleanup.'
    )
    parser.add_argument('repo', nargs='?', default='.', help='Path to the CRUMP-AI repository root')
    parser.add_argument('--check', action='store_true', help='Validate baseline and patches without writing')
    args = parser.parse_args()

    repo = Path(args.repo).expanduser().resolve()
    if not (repo / 'public').is_dir():
        print(f'ERROR: {repo} does not look like the CRUMP-AI repository root.', file=sys.stderr)
        return 2

    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    backup_root = PACKAGE_ROOT / f'BACKUP-{timestamp}'
    patched: dict[Path, str] = {}

    try:
        # Validate the five shell assets not touched by the earlier hardening package.
        # app.html is guarded by exact navigation fragments instead, so this cleanup
        # remains compatible whether the password-policy handoff ran first or second.
        for relative, expected_sha in EXPECTED_BASELINE_BLOBS.items():
            target = repo / relative
            if not target.exists():
                raise RuntimeError(f'Missing required file: {relative}')
            actual_sha = normalized_git_blob_sha(target)
            if actual_sha != expected_sha:
                raise RuntimeError(
                    f'{relative}: local file differs from the audited baseline '
                    f'(expected {expected_sha}, found {actual_sha}). Merge manually.'
                )

        for relative, patcher in PATCHERS.items():
            original = (repo / relative).read_text(encoding='utf-8')
            patched[relative] = patcher(original)

        test_relative = Path('tests/test_sidebar_navigation.py')
        test_source = PACKAGE_ROOT / test_relative
        test_target = repo / test_relative
        if not test_source.exists():
            raise RuntimeError(f'Handoff package is missing {test_relative}')
        if test_target.exists() and test_target.read_bytes() != test_source.read_bytes():
            raise RuntimeError(
                f'{test_relative}: a different test already exists. Merge it manually instead of overwriting.'
            )

        if args.check:
            print('Navigation cleanup validation passed. No files were written.')
            return 0

        for relative in PATCHERS:
            source = repo / relative
            destination = backup_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

        if test_target.exists():
            destination = backup_root / test_relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(test_target, destination)

        for relative, content in patched.items():
            (repo / relative).write_text(content, encoding='utf-8')

        test_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(test_source, test_target)

    except Exception as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        print('No files were written unless every baseline and patch validated first.', file=sys.stderr)
        return 1

    print('Ask Crump sidebar/navigation cleanup applied successfully.')
    print(f'Repository: {repo}')
    print(f'Backups: {backup_root}')
    print('Next: run pytest/npm tests, inspect the mobile sidebar, then review the GitHub Desktop diff.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
