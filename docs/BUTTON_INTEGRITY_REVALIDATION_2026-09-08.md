# Button integrity revalidation — 2026-09-08

## Outcome

Ask Crump's public account-entry actions, authenticated primary navigation, reversible dialogs,
creation destinations, Projects and Files handoffs, image and PowerPoint viewers, Library,
Settings, Plan & credits, Intelligence, and their close/back controls were revalidated after the
latest product releases. No dead product control was reproduced.

The only failures in the first local sweep were test-environment noise:

- public-page verifiers had initially been pointed at the repository root instead of the deployed
  `public` root; and
- three credential-free fixtures allowed the browser's automatic `/favicon.ico` request to return
  404 even though their tested controls completed correctly.

The public checks passed under production-equivalent routing. The three fixtures now declare a
no-network data favicon, and a regression assertion preserves that boundary so future console-error
failures represent the interaction under test.

## Automated acceptance

- The repository-wide static owner/type gate covered every button rendered in public HTML and
  JavaScript, including delegated dynamic systems.
- `tests/test_button_integrity.py`: **14 passed**.
- All **31** credential-free browser verifiers passed. The paid-plan timing matrix was reduced to
  one timing case per plan and viewport for this repeat pass; its full 40-case matrix had already
  passed in the preceding release gate.
- The public-page browser proofs passed for all five creation surfaces, the homepage Video handoff,
  marketing landing attribution/immutability, and guide preload behavior.
- Full Python suite: **895 collected**, **893 passed**, two environment-dependent tests skipped.
- JavaScript integration contract: **49 files** and **6/6** rough-to-useful runtime cases passed.
- Production preflight, native web build, Python compilation, and diff integrity passed.

## Release identity

- Commit: `4ea6cc5eebfddb121eae7f483632ec9d98249bf1`
- Main CI: `34258846758` — success.
- Automatic production deployment: `dpl_Fuzp37zmnHze6t6oa53dAbsqZT2n` — READY on all six
  aliases with no alias error.
- Canonical `/api/health`: HTTP 200 at version `5.9.76`.
- Initial 30-minute runtime-error aggregate: empty.

The commit changes only credential-free fixtures, their regression assertion, and release
documentation. Production application bytes and behavior are unchanged.

## Non-mutating production acceptance

The signed-in production pass opened and closed only reversible/read-only controls:

- Ask, Projects, Create, Video, Library, You, and Chats show/hide;
- the first conversation's options menu, without choosing Rename or Delete;
- Documents, Presentations, Images, Manuscripts, and Video creation destinations, without sending;
- Projects → Files, a foreground image viewer, a foreground PowerPoint viewer, Back to all
  Projects, and Close;
- Library Grid/List and Close;
- Settings Profile, Behavior, Account, About, and Plan & credits;
- the Plan & credits center and Close; and
- Intelligence and Close.

The PowerPoint viewer remained inside Ask Crump and exposed **Download to this device** instead of
navigating to private storage. No download was triggered. The image viewer rendered above Files,
and both viewers returned to the Files surface before Projects was restored.

## Safety boundary

No conversation was created, renamed, cleared, or deleted. No Project, manuscript, file, setting,
preference, account, session, purchase, checkout, download, generation, credit, analytics event,
campaign visit, publication, or customer record was created or changed. Destructive and financial
buttons remain covered through credential-free confirmation/recovery fixtures rather than being
executed against the founder account.

This is broad control-integrity evidence, not a claim that every future state, provider response,
browser version, or physical-device accessibility path has been exercised. Exact signed iPhone and
Android candidates still require their store-release interaction pass.
