# User-controlled conversation scrolling release — 2026-09-01

## Outcome

Ask Crump no longer moves the conversation viewport when the application renders or updates work.
The user's scroll position is authoritative until the user deliberately changes it.

The production behavior previously had competing owners: the base manager could move to the end,
the renderer requested the end for nearby or presence updates, both reply-completion paths requested
the end, and the final enhancement re-anchored each new assistant reply. Repeated renders around a
generated image could therefore pull the viewport to an earlier image while the user was scrolling.

The corrected contract now:

- preserves the current numeric conversation offset during every message-tree replacement;
- gives streaming text, presence indicators, completed replies, image completion/load, restored
  history, sync rerenders, and legacy scroll calls no authority to move the viewport;
- removes automatic send-time and completion-time end requests from both active message paths;
- retires the later new-assistant reply anchor and its timed hold state;
- keeps reserved image aspect dimensions and disables browser-native anchoring so image layout does
  not introduce a competing movement policy; and
- retains **Jump to newest message** as an explicit user-operated control. Manual wheel, touch, and
  scrollbar movement remain unchanged.

No message content, image, model, provider, prompt transformation, file, Project, credit, plan,
billing, account, database, analytics schema, campaign, or marketing surface changed.

## Release evidence

- Feature commit: `75151ea176913e712af599b3f603861124f228d1`.
- Production deployment: `dpl_8jtNzjMBLDiPzTbeonkyRQVb5471`, `READY`, current Production, built
  from the exact feature commit in 43 seconds with the expected six production aliases and no alias
  error.
- Exact web/PWA/native identities: `5.9.76-user-controlled-scroll-1`; runtime-loader identity:
  `5.9.76-user-controlled-scroll-loader-1`; service-worker cache:
  `ask-crump-new-body-v1-r201`.
- All four public Ask Crump/Clever Crump custom aliases returned the exact new loader. The two Vercel
  project aliases retained their configured Vercel authentication boundary. The canonical app,
  loader, base scroll manager, renderer, final scroll owner, service worker, and health endpoint all
  returned HTTP 200.
- A 390×844 real-browser fixture held `scrollTop=420` exactly through a presence update, a newly
  completed image reply, a streaming-text update, all retired legacy scroll calls, restored-history
  rendering, and a delayed generated-image load. The explicit newest-message control reached one
  pixel from the end and a later manual position held exactly. The image reserved a 1024×1536
  portrait box before load. Browser errors: zero.
- The signed-in production app loaded the exact versioned base manager, renderer, and final scroll
  owner, then rendered an existing private conversation containing two generated images and the
  explicit **Jump to newest message** control. No message, upload, generation, file, Project, credit,
  checkout, or account action was performed. Normal authenticated startup, sync, lifecycle, and
  analytics requests still occurred.
- All **741 Python tests**, **47 JavaScript validations**, Python compilation, production preflight,
  native web-bundle generation, store-metadata checks, mobile signing-source controls, and diff
  integrity passed.
- The exact deployment's visible 30-minute log window contained 44 API requests: 41 HTTP 200s and
  three expected signed-file HTTP 302 redirects, with zero 4xx/5xx response and zero
  warning/error/fatal console log.

## Remaining evidence boundary

Repeat long-history manual scrolling while a legitimate image or video finishes on the exact signed
iPhone and Android PWA/native candidates, including touch momentum, background/foreground, and
slow-network image load. No live generation was started during this release audit. Observe the
behavior with external users before claiming a reduction in abandonment, higher activation, or
retention lift. The repository still lacks generated Android/iOS projects and loaded RevenueCat
public SDK keys, so this release proves the production web/PWA and native web-bundle behavior—not a
signed store candidate.
