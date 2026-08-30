# Intelligence architecture, conversation privacy, and iOS icon release

Date: 2026-08-30

## Product outcome

- Intelligence now has four explicit responsibilities: Response effort, Memory & privacy,
  Live knowledge, and Quality review.
- Professional-only Think longer and Always review controls remain visibly attributable to
  Advanced Intelligence and retain the existing server entitlement boundary.
- The obsolete Web, Image, and Code quick controls and legacy composer mode strip are removed.
  Research routes directly through Ask, image creation opens Image Studio, attachments remain on
  the composer plus button, and creation work remains in Create.
- Crump Code has its own navigation destination, but it is hidden until both the feature and
  provider are configured. When configured for an ineligible account it opens the Professional
  plan review instead of appearing to run. Production remains intentionally unconfigured.
- A conversation-level memory opt-out is durable across signed-in devices. The server checks the
  stored opt-out independently of the browser and fails closed by skipping memory retrieval and
  learning whenever privacy state cannot be established.
- Clever Crump now declares the approved Ask Crump gold C/magnifying-glass mark as its 180px iOS
  Home Screen icon and has a dedicated Clever Crump standalone manifest.

## Privacy and data boundary

Supabase migration `20260830154409_conversation_memory_privacy` created the sparse
`public.chat_memory_opt_outs` table. A row contains only account ID, conversation ID, and
timestamps. RLS is enabled. `anon` and `authenticated` have no table privileges; only
`service_role` can select, insert, update, or delete. The browser accesses the setting through
authenticated account-scoped Python routes.

The Supabase post-change audit confirmed the intended privileges and introduced no performance
finding for this table. Its one informational security lint is the expected “RLS enabled with no
policy” notice: no browser role has grants, no client policy is intentionally present, and the
server role is the only access path.

## Verification

- Commit: `19a0b93`
- Production deployment: `dpl_BWiwJurc4HRjMDkuaRXav6CgzER8`
- Deployment state: `READY`, with aliases on both Ask Crump and Clever Crump canonical domains
- Python regressions: 579 passed
- JavaScript validation: 45 files plus the authenticated new-body integration contract passed
- Python lint and staged diff integrity passed
- Production preflight and native web-bundle build passed
- Live authenticated browser inspection confirmed the new Intelligence hierarchy, zero retired
  quick controls or mode strips, two hidden Code navigation controls, and the exact
  `5.9.76-intelligence-architecture-1` assets
- Live Clever Crump inspection confirmed both iOS touch-icon relations, the approved versioned
  180px asset, the dedicated manifest, the `Clever Crump` Home Screen title, and HTTP 200 JSON
  manifest delivery
- The post-deploy browser console was empty and Vercel reported no runtime-error cluster in the
  release window

No production conversation, memory preference, model run, Project, artifact, checkout, payment,
credit event, entitlement, or synthetic growth event was created for verification.

## Remaining evidence gates

- Have the owner delete the existing Clever Crump iPhone Home Screen shortcut and add it again;
  iOS caches installed icons and does not replace an existing shortcut reliably in place.
- Observe a legitimate cross-device conversation privacy change before claiming user adoption.
- Keep Crump Code unavailable until the separate live Sandbox/OIDC/destruction, cancellation,
  monitoring, rollback, cost, and benchmark gates are all proven.
- Run the existing real-task usability and physical-device accessibility checks before producing
  final native store screenshots.
