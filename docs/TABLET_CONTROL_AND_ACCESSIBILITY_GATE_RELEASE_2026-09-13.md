# Tablet control and accessibility gate release — 2026-09-13

## Outcome

Ask Crump's recurring interaction gate now covers the tablet layout class used by its iPad-capable
iOS target. A release can no longer pass solely because the same controls work at phone and desktop
widths.

## What changed

- `scripts/verify-tablet-destination-controls.cjs` runs the production navigation and Product Studio
  layers at 1024 by 1366 pixels.
- The journey exercises Ask, Projects, Create, Video, Library, You, and the nested Plan & credits
  action. It verifies the intended foreground surface and active destination after every tap.
- The journey fails on a sub-44-pixel persistent touch target, horizontal page overflow, a surface
  extending under the persistent navigation, a missing focus return, or any console/page error.
- The fail-closed browser inventory now requires 46 exact verifier files.
- The axe-core matrix now covers the same 11 public, capability, and account routes at phone,
  tablet, and desktop widths: 33 exact scenarios.
- The shared navigation fixture now loads the production Product Studio stylesheet. This prevents a
  mocked open state from being mistaken for proof that the surface is visibly usable.

## Verification

Feature commits: `ffd42d6762271a42779bf5c12f9595505ef043f7` and
`cd6b1fd9850edc732cc5952a97c3fdddb25c0f23`.

- Browser control matrix: 46/46.
- Public accessibility matrix: 33/33.
- Python: 1,051/1,051.
- JavaScript: 54/54, including the store packet's 21/21 embedded cases.
- Ruff, production preflight, native web bundle, client-credential scan, and diff integrity: passed.
- Vercel production deployment `dpl_F2FD8r3Ai9etikZx5oGmwBntDAHv`: Ready for the final exact commit.
- `www.askcrump.com`, `askcrump.com`, `www.clevercrump.com`, and `clevercrump.com` health: HTTP 200,
  version 5.9.76.
- Initial exact-deployment log sample: six HTTP 200 responses and no warning, error, or fatal log.
- GitHub CI `34792141565`: passed. The prior run `34791810559` correctly failed because the new test asserted an
  animation-frame focus handoff synchronously on Linux; `cd6b1fd` makes that timing contract
  explicit without weakening the required final focus.

The broader 30-minute production window contained one `/api/sync/push` 503 on the preceding
deployment at 00:05 UTC after an upstream database 504. It predates this release, is not a tablet
control failure, and does not justify retrying a non-idempotent write from one isolated event.

## Boundaries

This is deterministic browser and source evidence. It does not claim that every destructive,
payment, provider-generation, native-permission, or signed physical-device outcome has been
performed. Those retain their own user-controlled or store-release gates. The unsigned web bundle
was created successfully; this worktree intentionally does not contain generated Android/iOS
platform directories or owner-controlled public billing SDK keys, so signed native verification
remains separate.

No customer content, account, payment, credit, Project, file, generation, campaign, database row,
or external message was created or changed for this release.
