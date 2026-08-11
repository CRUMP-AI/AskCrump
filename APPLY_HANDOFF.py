from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
from pathlib import Path
import shutil
import sys

PACKAGE_ROOT = Path(__file__).resolve().parent

REPLACEMENTS = [
    Path('backend/email_service.py'),
    Path('backend/auth_service.py'),
    Path('backend/routes/auth.py'),
    Path('backend/routes/billing.py'),
    Path('backend/usage_service.py'),
    Path('requirements.txt'),
    Path('tests/test_release_hardening.py'),
    Path('tests/test_dependency_parity.py'),
    Path('tests/test_frontend_auth_policy.py'),
    Path('migrations/006_lock_public_data_api_to_service_role.sql'),
    Path('migrations/007_index_credit_ledger_related_ledger.sql'),
    Path('migrations/008_ensure_atomic_device_session_key.sql'),
]

EXPECTED_BASELINE_BLOBS = {
    Path('backend/email_service.py'): 'ab91f1f7bd15cd42b5108b1a14d624878cab39c0',
    Path('backend/auth_service.py'): '228f76520da7c238e7b96dde2cec27b41bab175c',
    Path('backend/routes/auth.py'): '64f0c58ba43c4257bd7f82ba44896d9fda7f8496',
    Path('backend/routes/billing.py'): '99b5e4ed6abd1b5e1eb7e43bd6cde77d46d56df1',
    Path('backend/usage_service.py'): 'd5fc8c9d13724275531f9dbdb4725cdae00af3bd',
    Path('requirements.txt'): '4545a17ec500999adc2bcf323de9f60724f974c0',
}

NEW_REPO_FILES = {
    Path('tests/test_release_hardening.py'),
    Path('tests/test_dependency_parity.py'),
    Path('tests/test_frontend_auth_policy.py'),
    Path('migrations/006_lock_public_data_api_to_service_role.sql'),
    Path('migrations/007_index_credit_ledger_related_ledger.sql'),
    Path('migrations/008_ensure_atomic_device_session_key.sql'),
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
            f'{label}: expected exactly one baseline match, found {count}. '
            'Your local file may differ from the audited commit; merge this change manually.'
        )
    return text.replace(old, new, 1)


def patch_app_html(text: str) -> str:
    text = replace_exact(
        text,
        '<input type="password" id="registerPassword" class="form-input" placeholder="At least 8 characters" required autocomplete="new-password">\n'
        '          <small class="form-hint">Minimum 8 characters</small>',
        '<input type="password" id="registerPassword" class="form-input" placeholder="10+ characters with a letter and number" required minlength="10" maxlength="256" autocomplete="new-password">\n'
        '          <small class="form-hint">At least 10 characters with a letter and a number</small>',
        'public/app.html registration password policy',
    )
    text = replace_exact(
        text,
        '<input type="password" id="registerPasswordConfirm" class="form-input" placeholder="Re-enter password" required autocomplete="new-password">',
        '<input type="password" id="registerPasswordConfirm" class="form-input" placeholder="Re-enter password" required minlength="10" maxlength="256" autocomplete="new-password">',
        'public/app.html registration confirmation constraints',
    )
    text = replace_exact(
        text,
        '<input type="password" id="newPassword" class="form-input" placeholder="At least 8 characters" required autocomplete="new-password">\n'
        '          <small class="form-hint">Minimum 8 characters</small>',
        '<input type="password" id="newPassword" class="form-input" placeholder="10+ characters with a letter and number" required minlength="10" maxlength="256" autocomplete="new-password">\n'
        '          <small class="form-hint">At least 10 characters with a letter and a number</small>',
        'public/app.html reset password policy',
    )
    text = replace_exact(
        text,
        '<input type="password" id="confirmNewPassword" class="form-input" placeholder="Re-enter password" required autocomplete="new-password">',
        '<input type="password" id="confirmNewPassword" class="form-input" placeholder="Re-enter password" required minlength="10" maxlength="256" autocomplete="new-password">',
        'public/app.html reset confirmation constraints',
    )
    return text


def patch_auth_controller(text: str) -> str:
    anchor = """  function setBusy(form, busy, label) {
    const button = form?.querySelector('button[type=\"submit\"]');
    if (!button) return () => {};
    const original = button.dataset.originalText || button.textContent;
    button.dataset.originalText = original;
    button.disabled = busy;
    button.textContent = busy ? label : original;
    return () => { button.disabled = false; button.textContent = original; };
  }
"""
    addition = anchor + """
  function validatePasswordInput(password) {
    if (password.length < 10) return 'Password must be at least 10 characters long.';
    if (password.length > 256) return 'Password is too long.';
    if (!/[A-Za-z]/.test(password) || !/\\d/.test(password)) {
      return 'Password must contain at least one letter and one number.';
    }
    return null;
  }
"""
    text = replace_exact(
        text,
        anchor,
        addition,
        'public/auth-controller.js password validator insertion',
    )

    text = replace_exact(
        text,
        """      const password = byId('registerPassword').value;
      if (password !== byId('registerPasswordConfirm').value) return setText('registerError', 'Passwords do not match.');
""",
        """      const password = byId('registerPassword').value;
      const passwordError = validatePasswordInput(password);
      if (passwordError) return setText('registerError', passwordError);
      if (password !== byId('registerPasswordConfirm').value) return setText('registerError', 'Passwords do not match.');
""",
        'public/auth-controller.js registration password validation',
    )

    text = replace_exact(
        text,
        """        const data = await response.json().catch(() => ({}));
        if (!response.ok || !data.success) throw new Error(data.error || 'Registration failed.');
        setText('registerSuccess', data.message || 'Account created. Check your email.');
        setTimeout(() => { hide('registerForm'); show('loginForm'); }, 1800);
""",
        """        const data = await response.json().catch(() => ({}));
        if (!response.ok || !data.success) {
          if (data.accountCreated && data.needsVerification) {
            const email = byId('registerEmail').value.trim();
            setText('registerSuccess', data.error || 'Account created, but verification email delivery is temporarily unavailable.');
            if (byId('loginEmail')) byId('loginEmail').value = email;
            setTimeout(() => {
              hide('registerForm');
              show('loginForm');
              show('verificationNeeded');
              setText('loginError', 'Your account exists but still needs email verification. Use Resend verification to try delivery again.');
            }, 2200);
            return;
          }
          throw new Error(data.error || 'Registration failed.');
        }
        setText('registerSuccess', data.message || 'Account created. Check your email.');
        setTimeout(() => { hide('registerForm'); show('loginForm'); }, 1800);
""",
        'public/auth-controller.js recoverable signup email failure handling',
    )

    text = replace_exact(
        text,
        """      const password = byId('newPassword').value;
      if (password !== byId('confirmNewPassword').value) return setText('resetPasswordError', 'Passwords do not match.');
""",
        """      const password = byId('newPassword').value;
      const passwordError = validatePasswordInput(password);
      if (passwordError) return setText('resetPasswordError', passwordError);
      if (password !== byId('confirmNewPassword').value) return setText('resetPasswordError', 'Passwords do not match.');
""",
        'public/auth-controller.js reset password validation',
    )
    return text


def backup_file(source: Path, backup_root: Path, relative: Path) -> None:
    if not source.exists():
        return
    destination = backup_root / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Apply the Ask Crump 2026-08-11 production-hardening handoff.'
    )
    parser.add_argument('repo', nargs='?', default='.', help='Path to the CRUMP-AI repository root')
    args = parser.parse_args()

    repo = Path(args.repo).expanduser().resolve()
    required = [repo / 'backend', repo / 'public', repo / 'migrations']
    if not all(path.exists() for path in required):
        print(f'ERROR: {repo} does not look like the CRUMP-AI repository root.', file=sys.stderr)
        return 2

    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    backup_root = PACKAGE_ROOT / f'BACKUP-{timestamp}'

    try:
        # Validate replacement baselines before touching the repository. This protects
        # newer local/backend work from being overwritten by an audited whole-file copy.
        for relative, expected_sha in EXPECTED_BASELINE_BLOBS.items():
            target = repo / relative
            if not target.exists():
                raise RuntimeError(f'Missing required baseline file: {relative}')
            actual_sha = normalized_git_blob_sha(target)
            if actual_sha != expected_sha:
                raise RuntimeError(
                    f'{relative}: local file differs from the audited baseline '
                    f'(expected blob {expected_sha}, found {actual_sha}). Merge manually.'
                )

        for relative in NEW_REPO_FILES:
            target = repo / relative
            source = PACKAGE_ROOT / relative
            if target.exists() and target.read_bytes() != source.read_bytes():
                raise RuntimeError(
                    f'{relative}: a different file already exists. Merge manually instead of overwriting it.'
                )

        # Patch the two large frontend files against the exact audited baseline.
        frontend_patchers = {
            Path('public/app.html'): patch_app_html,
            Path('public/auth-controller.js'): patch_auth_controller,
        }
        patched: dict[Path, str] = {}
        for relative, patcher in frontend_patchers.items():
            target = repo / relative
            if not target.exists():
                raise RuntimeError(f'Missing required target file: {relative}')
            original = target.read_text(encoding='utf-8')
            patched[relative] = patcher(original)

        # Back up every file that will be replaced or modified before writing.
        for relative in REPLACEMENTS:
            backup_file(repo / relative, backup_root, relative)
        for relative in frontend_patchers:
            backup_file(repo / relative, backup_root, relative)

        for relative in REPLACEMENTS:
            source = PACKAGE_ROOT / relative
            if not source.exists():
                raise RuntimeError(f'Handoff package is missing: {relative}')
            target = repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

        for relative, content in patched.items():
            (repo / relative).write_text(content, encoding='utf-8')

    except Exception as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        print('No frontend patch is written until all baseline checks pass.', file=sys.stderr)
        print(f'Any replaced-file backups are under: {backup_root}', file=sys.stderr)
        return 1

    print('Ask Crump hardening handoff applied successfully.')
    print(f'Repository: {repo}')
    print(f'Backups: {backup_root}')
    print('Next: install dependencies, run the verification commands in HANDOFF_SUMMARY.md,')
    print('review the GitHub Desktop diff, then commit only after all checks are green.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
