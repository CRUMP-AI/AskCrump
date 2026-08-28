# Ask Crump web-session handoff release — 2026-08-27

## Outcome

Ask Crump 5.9.29 repairs a production web-login failure in which valid credentials created a
server session but the browser remained on the sign-in screen and reported that the session could
not be established. No password, session token, or other credential was exposed during diagnosis.

## Production evidence

- A user-visible failure produced four successful `POST /api/auth/login` responses. Each login
  persisted or rotated a session, while its immediate `GET /api/auth/check-session` returned an
  unauthenticated result before consulting the session table.
- A later page load could still open the authenticated workspace. This isolated the failure to the
  cookie/session handoff rather than password verification, account state, or database availability.
- The failure pattern was consistent with a browser retaining both a legacy parent-domain cookie
  and a newer host-only cookie under the same name. The previous parser inspected only one value,
  and the client compounded the failure by rotating the session a second time after an invalid
  confirmation probe.

## Repair

- Bearer authentication remains authoritative and cannot fall back to browser cookies.
- Web authentication now inspects at most four deduplicated cookies with the configured session
  name and accepts only a candidate that maps to a live, unexpired, non-revoked session.
- Successful canonical web login clears the obsolete parent-domain cookie before issuing the
  host-only HttpOnly cookie. Logout clears both scopes.
- The client rotates the installation session exactly once, then performs three bounded,
  cache-free same-origin confirmation probes instead of issuing the credentials again.
- `device-auth.js` is release-versioned and network-first so an installed PWA cannot keep serving
  the stale handoff logic after the release reaches production.

## Verification

- Commit `38f7d11`; deployment `dpl_4H1xjuSyrC9dBxg5WWZ95jkfrox8` reached `READY` on all canonical
  production aliases.
- All 298 backend tests, backend lint, 40 JavaScript validations, production preflight, native web
  bundling, store metadata checks, Android 5.9.29/build 50929 source verification, and mobile
  signing-source controls passed locally.
- Hosted CI [33128276341](https://github.com/CRUMP-AI/AskCrump/actions/runs/33128276341), Android
  bundle verification [33128276312](https://github.com/CRUMP-AI/AskCrump/actions/runs/33128276312),
  and iOS Release compilation [33128276343](https://github.com/CRUMP-AI/AskCrump/actions/runs/33128276343)
  all completed successfully without signing or store upload credentials.
- Production health returned 5.9.29. The live app referenced `/device-auth.js?v=5.9.29`; the served
  script contained the single-rotation confirmation flow; the service worker used cache release
  `r63` and treated the auth asset as network-first.
- A live authenticated-browser reload opened the workspace with no session-establishment or
  sign-in error. The new deployment showed only HTTP 200 responses in the inspected window, no
  runtime error cluster, and no warning/error/fatal logs.

The exact new credential-entry path should still be rechecked by the owner after refreshing an
already-open sign-in tab. That confirmation does not require sharing a password with an operator.
