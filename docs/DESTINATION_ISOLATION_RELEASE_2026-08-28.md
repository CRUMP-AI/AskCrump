# Ask Crump 5.9.64 destination-isolation release

Date: 2026-08-28
Production version: 5.9.64
Feature commit: `bdef09505654e5b9d92e1ffc53f05e0eef8e0c59`
Production deployment: `dpl_5F2JeFyYrGwGvHaLuFqw66cwWyPm`

## Outcome

The five-destination navigation previously led into a second navigation system: Projects,
Manuscripts, and Video were still tabs inside one shared sheet. Library had already become a
dedicated destination, but the remaining internal tabs made Projects and Create feel redundant and
left the overall product organization incomplete.

Production 5.9.64 removes that internal tab bar. Projects, Manuscripts, Video Studio, and Library
now have distinct titles, accessible labels, active primary destinations, and exactly one visible
workspace at a time. Manuscripts and Video remain outcomes under Create. When Manuscripts has no
active Project, it offers an explicit `Open Projects` recovery instead of stranding the user.

## Scope and safety

- No Project, manuscript, file, conversation, account, generated artifact, or customer content was
  moved, copied, renamed, deleted, or migrated.
- Authentication, ownership checks, RLS, storage, synchronization, APIs, pricing, credits,
  entitlements, providers, payments, and analytics semantics did not change.
- Files remains the reference-file attachment action; Chats remains conversation history.
- The release removes obsolete markup, keyboard-tab behavior, and three layers of dead tab styling
  instead of hiding redundant controls with another visual override.
- Production verification inspected structure and destination state only; it did not record or
  reproduce private titles, filenames, prompts, messages, or generated content.

## Verification

### Local contracts and build

- All 395 Python tests passed.
- Ruff passed across backend, tests, and scripts; backend compilation passed.
- All 44 JavaScript source and integration validations passed.
- Production preflight, the native web bundle, store metadata validation, mobile signing-source
  checks, Android synchronization, Android configuration, and Android native-source verification
  passed.
- The local Windows environment still cannot create or validate the Xcode iOS project; the hosted
  macOS iOS source-verification gate passed below.

### Isolated browser fixture

- Library opened one `Ask Crump Library` dialog with one visible Library panel, the manuscript
  bookshelf, saved-file grid, correct primary active state, and zero internal workspace tabs.
- Projects opened one `Ask Crump Projects` dialog with only the Projects panel visible.
- Create opened Manuscripts and Video Studio as separately titled focused workspaces while keeping
  Create active.
- With no active Project, Manuscripts exposed `Open Projects`; activating it opened Projects and
  changed the primary active destination to Projects.
- Files executed the fixture attachment action exactly once and did not open Library.
- At 390 by 844 pixels, Library, Manuscripts, Projects, and Video Studio stayed within the viewport;
  the sheet measured exactly 390 pixels wide and contained horizontal overflow.

### Hosted gates

- CI: [run 33207125922](https://github.com/CRUMP-AI/AskCrump/actions/runs/33207125922) — passed.
- Android store bundle: [run 33207125976](https://github.com/CRUMP-AI/AskCrump/actions/runs/33207125976) — passed.
- iOS store source: [run 33207125988](https://github.com/CRUMP-AI/AskCrump/actions/runs/33207125988) — passed.

### Production

- Git deployment `dpl_5F2JeFyYrGwGvHaLuFqw66cwWyPm` reached READY on production and serves
  commit `bdef095` through `askcrump.com` and `www.askcrump.com`.
- `https://www.askcrump.com/api/health` returned HTTP 200 and version 5.9.64.
- The live service worker returned HTTP 200 with cache `ask-crump-new-body-v1-r98` and 5.9.64
  versioned assets.
- In the authenticated production shell, Projects, Library, Manuscripts, and Video Studio each
  exposed one visible panel, the correct dialog label/title, the correct primary active
  destination, and zero internal tabs.
- Live Library contained both the bookshelf and saved-file surfaces without outputting private
  content.
- At a live 390-by-844 viewport, Video Studio measured 390 pixels from edge to edge with contained
  horizontal overflow and no internal tabs.
- Vercel reported no runtime error cluster and no warning, error, or fatal deployment log in the
  inspected 30-minute release window.

## Outcome still to prove

The release verifies a simpler, internally consistent product hierarchy. It does not yet prove
faster destination discovery, higher Project creation, greater Library reuse, artifact completion,
or improved return behavior. Those outcomes require legitimate post-release use and content-free
aggregate evidence.
