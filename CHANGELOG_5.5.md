# Ask Crump 5.5 — Video Engine

Ask Crump 5.5 turns video generation from a single-provider novelty into a durable creative subsystem. Quick keeps the existing Veo Lite experience, Extendable uses Veo 3.1 Fast so a finished scene can continue from its endpoint, and Cinematic adds an optional Runway Gen-4.5 path without exposing provider secrets to the client.

Continuation jobs preserve parent/root lineage, duration, provider references, cost estimates, and storage safety metadata. Compatible completed videos can continue directly from the result or Saved Library while each new combined output is copied into Ask Crump's private storage.

The release also adds server-side provider-spend circuit breakers that remain active even when an internal founder entitlement bypasses Ask Crump credit metering. Runway stays disabled until its server secret is deliberately configured.

Because the connected production Supabase organization currently uses the Free plan, the generated-video safety ceiling defaults to 45 MB. The limit can be raised after production storage capacity is intentionally upgraded.

This release fixes the existing Windows JavaScript validation defect by converting file URLs into native Windows paths before passing them to Node.
It also makes the production preflight resolve its repository root from the script location, so validation is independent of the folder that launched Node or PowerShell.

The default provider circuit breakers are $100/day across video generation, $20/day per non-internal user, and $500/month for Runway. Internal founder access bypasses only the per-user ceiling; global/provider ceilings remain active and can be raised deliberately through server environment settings.
