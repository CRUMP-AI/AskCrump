# Sanitized demo-account recording workflow

Status: operator workflow; no customer-facing account behavior changes.

Use this workflow to prepare authentic Ask Crump recordings without exposing a founder account, a customer account, or private material. The fixed identity is `demo@askcrump.com` with the generic display name `Ask Crump Demo`.

## Safety boundary

- The command is read-only unless `--replace` is explicitly supplied.
- Replacement is restricted to the one fixed email address; the email cannot be changed by an argument.
- An existing row must already match the protected internal-demo contract: verified, internal enterprise entitlement, preview environment, free/inactive billing state, generic name, and no Stripe, store, or subscription identity.
- The operator must type `REPLACE demo@askcrump.com` exactly.
- The new password is read twice through a hidden terminal prompt. It is never accepted as a command-line argument, printed, or written to a file.
- Private Supabase Storage objects are deleted through the existing file service before the account row is removed. If file cleanup is incomplete, account replacement stops.
- The account row is deleted through the service-role-only `delete_user_account` function, which cascades user-owned database rows and invalidates sessions.
- The replacement account is marked `registration_environment=preview` and `internal_tier=enterprise`, so it is excluded from customer growth and lifecycle reporting.
- No `AccountCreated` analytics event is emitted, and the account has no billing entitlement or provider identity.
- Inspection also verifies the generic profile, empty profile preferences, and default workspace settings. A content-free account with a customized profile is not considered recording-ready.
- Automated schema-parity coverage fails if a newly migrated user-owned table is not assigned to a clean-state inspection category.

## Required operator environment

Run from the repository root with backend-only values already present in the local process:

```powershell
$env:SUPABASE_URL = "https://YOUR_PROJECT.supabase.co"
$env:SUPABASE_SERVICE_KEY = "YOUR_BACKEND_ONLY_KEY"
```

Use a Supabase secret key (`sb_secret_...`) or the legacy service-role JWT. A publishable or anonymous key is rejected. Never place either backend value in a browser bundle, screenshot, recording, committed file, or chat.

## Inspect without changing anything

```powershell
python scripts/manage_demo_account.py
```

The output contains only fixed identity status, profile-default status, recording readiness, and category-level presence. It does not display account IDs, filenames, project names, prompts, messages, or other content.

## Reset immediately before a recording session

```powershell
python scripts/manage_demo_account.py --replace --receipt docs/demo-clean-state-YYYY-MM-DD.json
```

1. Review the read-only status printed first.
2. Type the exact replacement acknowledgement when prompted.
3. Enter a new strong password twice through the hidden prompt.
4. Wait for `Customer-content state: clean`, `Profile defaults: yes`, `Recording ready: yes`, and the completion message.
5. Preserve the newly created JSON receipt with the recording evidence. It contains only the fixed demo identity, clean category names, exclusion flags, and reset counts—never credentials, account IDs, filenames, prompts, or customer content. Existing receipt files are never overwritten.
6. Sign in at Ask Crump with the fixed demo email and the password chosen in step 3.

The reset invalidates any previous demo sessions. Do not run it while someone is actively recording from this account.

For a read-only evidence refresh after the account is already clean, omit `--replace` and keep `--receipt`. Receipt creation fails closed unless the account is fully recording-ready.

## Recording rules

- Use only invented, generic business material. Never paste customer, employee, founder, payment, or production incident data.
- Keep filenames and project names generic, such as `Launch plan demo` or `Quarterly review demo`.
- Record real product behavior continuously. Do not splice together states that imply a feature performed an action it did not perform.
- Hide browser bookmarks, notifications, password managers, other tabs, and operating-system account details.
- Do not show this terminal, environment variables, cookies, request headers, account settings, billing pages, or internal analytics.
- Use the current canonical Ask Crump lockup. Do not reintroduce the retired `AI virtual assistant` descriptor.
- Reset the demo account again before the next campaign if prior demo material should not appear.

## Recommended proof sequence

1. Submit a short, generic request and show the useful response.
2. Save the work to a Project.
3. Leave the workspace, reopen that Project, and show continuity.
4. Generate an editable document or PowerPoint artifact and inspect the real output.
5. End on the live product surface; add campaign logos or captions only in post-production.

This workflow prepares product evidence. It does not authorize publication, paid spend, profile edits, or campaign launch.
