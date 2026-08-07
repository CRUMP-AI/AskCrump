# Ask Crump 5.2.4 — Identity & Session Stability

- Rotates an existing session row when the same installation signs in again.
- Prevents `sessions_device_id_unique` conflicts from blocking valid logins.
- A successful login can safely move an installation from one account to another.
- Restores the full Ask Crump horizontal wordmark in the main conversation header.
- Uses the horizontal wordmark on authentication screens.
- Preserves the 5.2.2 stable scrolling behavior and 5.2.3 billing recovery.

No database migration is required.
No environment-variable changes are required.
