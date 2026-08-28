# Ask Crump 5.9.54 transport-log privacy containment release

Date: 2026-08-28

Production version: 5.9.54

Code commit: `44b0efa111f9d64c6f4452ed31c332edcfd53ded`

Production deployment: `dpl_GSm6EFkPN6EpKCqrVV77WKTbQ8tt`

## Outcome

Dependency-level HTTP request records can no longer emit full Supabase filter URLs into Ask Crump's
application runtime logs. Those URLs can contain opaque session hashes and internal account,
Project, chat, or file identifiers. Ask Crump's content-free categorical auth outcomes remain
available for operations.

Database exception logging now records only status and detail type, not the raw upstream detail
payload. No authentication policy, cookie, session, database row, RLS rule, analytics event,
entitlement, payment, provider, or customer-facing workflow changed.

## Production evidence that identified the gap

A read-only production log review on 2026-08-28 found that the app-owned authentication logger was
identity-free, but `httpx` INFO records still included complete Supabase request URLs. The affected
records exposed opaque session-token hashes and internal row identifiers in log metadata.

The earlier 5.9.49 protection set the dependency logger levels during application import. The live
evidence showed that the serverless host could apply or restore its own logging configuration after
that point. The earlier categorical auth logging remains valid, but import-time suppression alone
was not a sufficient production privacy boundary.

No production secret, hash, or internal identifier from the discovered records is copied into this
release document.

## Correction

- Added one allowlist-independent privacy filter that rejects every record whose logger name is
  `httpx`, `httpcore`, or one of their child loggers.
- Applied the filter to root handlers, transport-specific handlers, and current transport loggers.
- Reasserted the boundary at the start of every request, after host logging setup and before any
  route can reach Supabase.
- Kept Ask Crump's own categorical diagnostics available.
- Replaced raw `DatabaseError.details` logging with status and detail-type categories.
- Advanced the application to 5.9.54, native build 50954, and PWA cache revision 88.

## Full-story verification report

| Boundary | Status | Evidence |
| --- | --- | --- |
| Host logging reset | Passed | The regression test re-enabled `httpx` INFO logging and installed a transport-specific handler after app configuration. |
| Request entry | Passed | The real request middleware reapplied the privacy boundary before downstream work. |
| Transport record | Passed | A full Supabase-style URL containing a private sentinel session hash produced no emitted transport text. |
| Categorical operations | Passed | `Auth session outcome=authenticated client=web` remained visible in the same logging test. |
| Database exception | Passed | A synthetic upstream detail containing session/user sentinels was absent while status and detail type remained visible. |
| Production transport | Passed | A non-writing fake-cookie request forced a real Supabase session lookup on the exact deployment; neither the fake sentinel hash nor `HTTP Request:` appeared in the deployment logs. |
| Production operations | Passed | The same request returned HTTP 200 with `authenticated:false`, and the deployment log retained `Auth session outcome=unauthenticated client=web`. |

The production probe used a deliberately fake session cookie and created no account, session,
message, Project, payment, analytics event, or database write.

## Automated and native verification

- 371 Python tests passed.
- Ruff passed for `backend` and `tests`; Python compilation passed for `backend` and `app.py`.
- All 44 JavaScript files passed syntax and integration validation.
- Production preflight and the native web-bundle build passed.
- Android source verification passed for Ask Crump 5.9.54, build 50954, and API 36.
- Store metadata and tracked-signing-secret controls passed.
- GitHub CI run `33172015491` passed.
- Hosted unsigned Android App Bundle run `33172015490` passed.
- Hosted unsigned iOS Release compile run `33172015531` passed.

The local verifier correctly reports that the iOS project is absent on Windows. RevenueCat public
keys, Android Firebase, signing credentials, physical-device results, and store submission remain
separate open gates.

## Production evidence

- Deployment `dpl_GSm6EFkPN6EpKCqrVV77WKTbQ8tt` reached `READY` from the exact code commit.
- `https://www.askcrump.com/api/health` returned HTTP 200 and version 5.9.54.
- The live app and service worker returned HTTP 200; the app exposed 5.9.54 and the worker served
  `ask-crump-new-body-v1-r88`.
- The fake-cookie Supabase lookup retained one identity-free auth outcome and exposed no transport
  URL or sentinel hash in the exact deployment logs.
- The one-hour project scan contained no runtime error cluster, and the exact deployment contained
  no warning, error, or fatal log.

## Rollback

The prior production deployment `dpl_2YgUGbuyLnQH9GhU2tB99nJgckTD` remains available. Rollback would
restore the dependency-log exposure, so it should be used only if a separate critical production
failure outweighs that privacy risk. This release requires no schema, RLS, environment,
authentication, payment, pricing, or infrastructure migration.

## Remaining evidence

Monitor the next legitimate authenticated session and Project workflow for categorical operational
coverage without URL-bearing dependency records. Retain current log access controls and avoid
copying any older identifier-bearing record into tickets or reports.
