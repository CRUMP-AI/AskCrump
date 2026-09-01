# Constrained rewrite fidelity release — 2026-09-01

## Outcome

Ask Crump now treats an explicit request to preserve facts while rewriting, reorganizing, or
reformatting supplied material as a constrained transformation. Before the primary answer, the
server builds a bounded, current-request-only fidelity ledger that keeps modality-bearing source
spans and explicit audience spans adjacent to the model. The contract distinguishes **should** from
**must** and requires named readers, recipients, roles, and quantities to remain visible rather than
merely implied.

Under the default automatic verification setting, every constrained transformation also receives a
final-answer review even when the request otherwise uses balanced mode. That review is specifically
forbidden from accepting a draft that strengthens or weakens modal language or drops an explicit
audience. Unconstrained conversation does not create the ledger or trigger this new review path.

## Privacy and cost boundaries

- The ledger is derived from the current request in memory. It is not added to analytics, traces,
  synchronized messages, or a new database record.
- The existing tier-aware verifier remains authoritative: free accounts stay on the configured free
  gateway and never fall through to paid Anthropic merely because fidelity review is required.
- The frozen marketing fixture was not submitted again during this release. No provider request,
  credit, customer record, Project, file, campaign, publication, or spend was created.
- This release is a targeted product correction, not proof that every future transformation will be
  perfectly faithful. The separately controlled same-fixture rerun and human review remain required.

## Executable regression coverage

The regression proves the complete internal handoff for the two observed defects:

1. a constrained source sentence containing **the workshop should happen within six weeks** is
   retained in the fidelity ledger and sent to the primary model;
2. **two volunteers** is retained as an explicit audience and sent to the primary model; and
3. a mocked bad draft that says **must happen within six weeks** and omits the audience is forced
   through the automatic verifier, which returns **should happen within six weeks** and explicitly
   restores **two volunteers**.

It also proves that an ordinary question using “should” does not activate the constrained-rewrite
path.

## Verification

- All **753 Python tests** passed.
- All **48 JavaScript files** passed the repository contract gate.
- Focused intelligence/identity coverage passed **28/28**.
- Python compilation and Ruff passed for the affected implementation and test files.
- Production preflight, native web-bundle creation, store metadata, mobile signing-source controls,
  and Git diff integrity passed.
- Both canonical Ask Crump health endpoints returned HTTP 200 with service version **5.9.76** after
  the release became READY.
- Vercel reported no runtime-error cluster in the inspected 30-minute production window.

## Release identity

- Behavior commit: `f721d3b952e21149b8595e9b3577cefa4c1ce18d`
- Production deployment: `dpl_DWRdZsECf4bQRv24Pwm7yCNhv1uT`
- Status: `READY` on all six aliases
- Frozen failed rendered-output evidence remains unchanged at SHA-256
  `73BEB48BB51EBD226E93372BC2121DF7B9230E3E1FF2A75BE1D29A068564E551`.
- Marketing's separately owned 20-check verifier was received at SHA-256
  `0024D291B432AB5E873419735F01F013163071BBD9B6C547B5203EF8E575281D` but was not used to rerun
  the product fixture.

## Remaining acceptance gate

Return this exact product evidence to marketing. A separately authorized operator may then perform
one same-fixture production rerun, extract the complete rendered response, run the verifier without
its synthetic switch, and complete the human fidelity/privacy review. Publication remains held
unless all of those gates pass.
