# Destination ownership and retired Tools menu — 2026-08-30

## Outcome

Ask Crump no longer presents a redundant Tools menu in the signed-in composer. The product now
uses one clear ownership model:

- **Ask** is the default conversation workspace.
- **Intelligence** owns research/current-information and answer-quality controls.
- **Create** owns Documents, Presentations, Images, Manuscripts, and Video.
- The composer **+** button owns file attachment.
- **Crump Code** remains a separate, hidden destination until its safety, quality, cost, and owner
  activation gates pass.

The original mode buttons remain hidden in the document only as compatibility targets for older
internal commands. They are not focusable, announced, or visible, and the legacy Tools trigger,
menu, option metadata, and styling were removed.

## Release evidence

- Feature commit: **b65fb73be8ba0a1f7f6cc0e0cf9cff8bdc212b02**
- Production deployment: **dpl_8MjtK6oMgng3fNJkBUbFELrroA2N**
- Production state: **READY**, with the six expected aliases and no alias error.
- The live **www.askcrump.com** application shell returned HTTP 200 with the hidden compatibility
  strip and exact **5.9.76-destination-tools-1** runtime.
- The live product JavaScript returned HTTP 200, contains **retireLegacyToolStrip**, and contains
  neither **crump53ToolTrigger** nor **crump53ToolMenu**.
- The live product CSS returned HTTP 200 with the forced hidden-strip rule and no retired menu
  styling.
- The live service worker returned HTTP 200 with cache **ask-crump-new-body-v1-r160** and the exact
  destination-tools assets.
- The release window had no Vercel runtime-error cluster and no warning, error, or fatal runtime
  log for the deployment.

## Verification

- All 569 Python tests passed.
- All 45 JavaScript files passed the integration contract.
- Production preflight and native web-bundle generation passed.
- A credential-free real-browser fixture proved:
  - no Tools trigger or menu exists;
  - the compatibility strip is hidden and **aria-hidden**;
  - Create opens Documents, Presentations, Images, Manuscripts, and Video;
  - the primary navigation remains Ask, Chats, Projects, Create, Library, and You;
  - no browser error was recorded.
- Release guards now fail if the old Tools trigger, menu, or enhancement code returns.

The native verifier retained only the pre-existing store prerequisites: the local Windows checkout
does not contain an iOS project, RevenueCat Android and iOS public SDK keys were not supplied to
the native build, and Android Firebase configuration is absent. These are submission gates, not
regressions from this web/PWA release.

## Boundaries

This release did not activate Crump Code, change pricing, quotas, credits, subscriptions,
entitlements, checkout, providers, prompts, or model routing. It created no production account,
message, artifact, Project, payment, checkout, credit event, model run, or synthetic analytics
event. Delivery evidence does not establish activation, retention, or conversion lift.

## Next decision

Preserve this destination model while observing legitimate first-use behavior. The next product
change should be driven by a real first-visit → registration → useful answer → durable keep or
return journey, rather than adding another top-level capability surface.
