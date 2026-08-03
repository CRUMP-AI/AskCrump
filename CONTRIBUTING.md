# Contributing

Ask Crump is currently maintained as a founder-led product. Changes should be small, reviewable, and tied to a documented product or reliability need.

## Development workflow

1. Create a focused branch from `main`.
2. Keep server-authoritative behavior on the Python side.
3. Do not introduce a second authentication, storage, or billing path.
4. Add or update tests for behavioral changes.
5. Run the full local quality checks before opening a pull request.

```bash
ruff check app.py backend tests
python -m compileall -q app.py backend
pytest -q
npm run test:js
```

## Pull requests

A pull request should explain:

- the user problem;
- the implementation choice;
- security, privacy, and migration implications;
- the tests performed;
- any owner-controlled deployment steps.

Avoid unrelated formatting changes, generated artifacts, credentials, native signing files, and broad rewrites without an architecture decision record.
