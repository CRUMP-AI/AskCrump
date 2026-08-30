# Truthful public destinations release

Date: 2026-08-30
Production version: `5.9.76`

## Outcome

Ask Crump's public site now teaches the same five-destination structure as the signed-in
product: Ask, Projects, Create, Library, and You. Library is described only as the private
bookshelf for manuscripts and books. Generated documents, resumes, images, video, exports, and
uploads are directed to Projects → Files instead of a generic Library.

This removes a first-visit expectation gap that could make an accurate product feel broken. It
also gives prospective users a restrained product preview that shows where work goes before they
commit to registration.

## Public contract

- Ask contains conversations, decisions, and guided research.
- Projects keeps instructions, context, conversations, and generated or uploaded work together.
- Create opens the dedicated document, presentation, image, video, and manuscript paths.
- Library is solely the private bookshelf for manuscripts and books.
- You contains plan, session, restoration, privacy, and account controls.
- The document and resume pages explain download plus the deliberate Keep in a Project action.
- The video page directs completed clips to Projects → Files.
- Clever Crump's product-system preview names Library as Books + manuscripts.

No authentication, billing, entitlement, pricing, plan allowance, private data, or generation
behavior changed.

## Verification

- All 521 Python tests passed.
- All 45 JavaScript files passed the repository integration validator.
- Focused public-destination, company-page, conversion, canonical-domain, product-polish, and
  static-asset checks passed.
- Diff integrity passed.
- A local browser pass verified the complete accessible product-preview structure and its visual
  hierarchy before release.
- The live browser then verified the same five destinations, exact storage boundaries, internal
  capability links, and restrained desktop presentation.
- The home, document, resume, video, parent-company, both sitemap, and health routes returned HTTP
  200 from their canonical production domains.
- Exact live-string checks found the new Project Files and books-only Library language and found
  none of the replaced private-Library promises.

## Production release

- Feature commit: `306f6ad`
- Deployment: `dpl_GMiiXaJZnbx9iheEAfZJbtsfKUAA`
- Deployment state: `READY`
- Alias state: six production aliases, no alias error
- Service-worker cache: `ask-crump-new-body-v1-r146`
- Public stylesheet boundary: `5.9.76-truthful-destinations-1`
- Canonical health: HTTP 200, service `Ask Crump`, version `5.9.76`

The deployment-scoped production check observed successful responses and no 5xx response after
the release became ready.

No production account, message, Project, file, manuscript, video, purchase, subscription,
checkout, payment, or synthetic funnel event was created for verification.

## Next operating decision

Keep the public promise aligned with the product while acquiring the first comparable external
users. The next change should improve a measurable first-visit, registration, activation, or
return-work boundary rather than add an unproven surface area.
