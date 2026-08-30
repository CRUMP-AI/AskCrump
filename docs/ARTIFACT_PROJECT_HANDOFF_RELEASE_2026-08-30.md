# Generated artifact to Project handoff release

Date: 2026-08-30  
Production version: `5.9.76`

## Outcome

A generated document can now move into a Project with the conversation that produced it.
The artifact card presents two independent actions:

- **Add to Project** preserves the source conversation and attaches the owned generated file to
  the same Project;
- **Download** keeps the existing direct-download path unchanged.

After the Project handoff succeeds, the first action becomes **Open Project** and returns to the
exact destination containing the work.

## Evidence and decision

The protected production growth and artifact reports did not yet contain a comparable external
cohort from which to diagnose a real conversion drop. The production error review found only a
superseded manuscript-scheduler signal already addressed by the replay-safe claim release; the
current deployment was clean.

A deterministic activation audit then found that the existing continuity action attached the
conversation to a Project but did not place its generated document in that Project's Files
section. The artifact remained recoverable through the conversation, but it was absent from the
dedicated durable-file surface. This release closes that gap without manufacturing activity.

## Product contract

- The browser sends only the existing owned file identifier and the fixed
  `generated_document` role.
- The existing authenticated Project route rechecks both Project ownership and file ownership.
- The existing `project_files` primary key makes retrying the same attachment duplicate-safe.
- If no Project is active, the existing conversation-to-Project path creates or reuses the
  appropriate workspace before attaching the file.
- If a Project is active, the same path attaches the conversation and file to that destination.
- A failed file attachment does not erase the already-preserved conversation, and the user can
  safely retry.
- Nested work suppresses duplicate success/failure notices and duplicate list refreshes.
- No prompt, response, filename, URL, customer identifier, credential, or free-form analytics
  value was added to telemetry.

## Verification

- All 497 Python tests passed.
- All 45 JavaScript files passed the repository integration validator.
- Production build preflight passed.
- The native web bundle was rebuilt successfully.
- Store metadata source verification passed.
- A credential-free browser fixture executed the real client controllers and proved:
  - the conversation save occurs before file attachment;
  - the file is attached with role `generated_document`;
  - **Add to Project** becomes **Open Project** only after success;
  - **Download** remains visible and enabled;
  - the production-styled desktop card is coherent;
  - no browser error occurred.
- Diff integrity passed.

The native release verifier continued to report the pre-existing store-submission gates: the iOS
native project and the RevenueCat/FCM release configuration are not yet present. Those gates are
unrelated to this web/PWA change and remain explicitly unclaimed.

## Production release

- Feature commit: `46988f9`
- Immediate-loader correction: `3c7705d`
- Final deployment: `dpl_49vUbumys2VH3HMAXmC6W48sNWts`
- Deployment state: `READY`
- Alias state: six production aliases, no alias error
- Service-worker cache: `ask-crump-new-body-v1-r142`
- Runtime and changed assets: `5.9.76-artifact-project-1`
- Canonical health: HTTP 200, service `Ask Crump`, version `5.9.76`

The canonical app loaded the new top-level runtime identity. The exact live runtime, artifact
renderer, Project controller, stylesheet, and service worker all returned successfully and
contained their expected release markers. After the deployment had been ready for more than one
minute, the inspected window contained only successful responses, no runtime-error cluster, and
no warning, error, or fatal log.

No production account, Project, conversation, file attachment, artifact, payment, checkout, or
synthetic funnel event was created for verification.

## Next operating decision

Observe the first legitimate production artifact request through packaging and either Project
retention or download. Reconcile the content-free artifact journey and durable-value milestones
before changing the interaction again or scaling acquisition spend.
