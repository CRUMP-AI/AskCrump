# Application dependency security release — 2026-09-13

## Outcome

Ask Crump no longer deploys the Python dependency versions identified by the
current vulnerability audit in its multipart upload, PDF parsing, and ASGI
request stack. The production pins now use:

- FastAPI 0.141.1;
- Starlette 1.3.1;
- python-multipart 0.0.32; and
- pypdf 6.18.1.

The initial requirements audit reported known advisories against
python-multipart 0.0.20, pypdf 6.14.2, and Starlette 0.47.3. The exact updated
production requirements now return `No known vulnerabilities found` from
pip-audit 2.10.1. CI installs the same pinned audit tool and evaluates
`requirements.txt` on every main-branch push and pull request, so a later
dependency regression fails the release pipeline.

The exact committed npm lockfile was also audited with the registry-published,
integrity-verified npm 12.0.2 client. Both the complete dependency tree and the
production-only tree reported zero informational, low, moderate, high, or
critical vulnerabilities. CI now runs an explicit lockfile audit at the
moderate threshold after deterministic installation; the existing `--no-audit`
install flag remains only to avoid duplicating the scan during installation.

FastAPI's current package metadata supports Starlette 1.x. Starlette 1.3.1 was
selected as the conservative fixed boundary because it enforces form field and
part-size limits, while the immediately following 1.4.0 release had a documented
downstream gzip-constructor regression. Primary references:
[FastAPI 0.141.1](https://pypi.org/project/fastapi/),
[Starlette release notes](https://github.com/Kludex/starlette/blob/main/docs/release-notes.md),
[python-multipart 0.0.32](https://pypi.org/project/python-multipart/), and
[pypdf 6.18.1](https://pypi.org/project/pypdf/6.18.1/).

## Compatibility correction

FastAPI 0.141.1 represents included routers lazily. Three route-contract tests
previously inspected only eager top-level route objects and therefore reported
missing routes even though the live HTTP and OpenAPI surfaces remained present.
The shared test helper now traverses both eager routes and the framework's
effective included-route contexts. It preserves the original fail-closed route
inventory rather than weakening or deleting the checks.

## Verification

- A new isolated Python 3.12 environment was created from the exact revised
  `requirements-dev.txt`; dependency installation and `pip check` passed.
- The complete application suite passed 1,049/1,049 in that isolated
  environment.
- The exact revised `requirements.txt` passed pip-audit 2.10.1 with no known
  vulnerabilities.
- The complete and production-only npm lockfile audits each reported zero
  vulnerabilities at every severity.
- JavaScript validation passed 54/54.
- Ruff, production preflight, native-web bundling, and the client-credential
  boundary passed.
- Focused dependency parity and route-contract coverage passed 23/23.

## Production evidence

- Feature commit: `1780c7b459105b20cb79141559ee99f32f0d71a8`.
- Production deployment: `dpl_CzdD6KCrMqZwxx6KizaeNQQ8TXZp` — Ready on all
  six expected aliases with no alias error.
- GitHub Actions run `34784081233` passed, including the new production
  dependency audit, Python 3.12 suite, and JavaScript release gates.
- The exact-release browser control matrix passed 45/45, covering navigation,
  Projects, Files and viewers, image editing and stability, Video and reference
  images, Library, Settings, account entry and recovery, plans, credits, and
  checkout recovery.
- `www.askcrump.com`, `askcrump.com`, `www.clevercrump.com`, and
  `clevercrump.com` health returned HTTP 200 at version 5.9.76.
- The first deployment-scoped production log sample contained four HTTP 200
  responses and no grouped runtime error.

## Deliberate boundaries

This release changes pinned Python packages and test introspection only. It does
not add a client-facing database policy, alter customer content, change upload
limits or accepted file types, create an account, charge a customer, or invoke
an AI provider. The clean vulnerability scan proves the current published
advisory boundary; it does not promise that dependencies can never receive a
future advisory. The new CI gate provides the corresponding recurrence check.
