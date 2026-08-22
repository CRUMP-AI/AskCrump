# Ask Crump 5.7.2 — Navigation Reliability

Ask Crump 5.7.2 is a focused product-reliability release that restores dependable access to the account, billing, and Projects surfaces from the authenticated sidebar.

## Fixed

- Settings now opens even when late UI hydration has replaced the original sidebar element or lost its listener.
- Plan & credits now reliably reaches the billing center, protecting the upgrade and credit-purchase path.
- Projects now reliably opens the Projects & Create workspace from its sidebar destination.
- Existing product handlers remain primary; a guarded zero-delay fallback runs only if the intended surface is still closed.
- Library supporting copy now uses the canonical muted-text theme tokens instead of an undefined variable.

## Delivery safeguards

- The navigation JavaScript and CSS are now part of the core service-worker cache.
- Both navigation assets use network-first delivery as boot-critical application resources.
- The service-worker cache advanced to `ask-crump-new-body-v1-r27`.
- Automated contracts cover each repaired destination, service-worker delivery, and frontend/backend version parity.
