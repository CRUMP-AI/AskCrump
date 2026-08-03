# Security Policy

## Reporting a vulnerability

Do not open a public issue for a suspected vulnerability. Use GitHub private vulnerability reporting when it is enabled for the repository. Otherwise, contact the repository owner privately using the contact information on their GitHub profile. Include:

- the affected endpoint or component;
- reproduction steps;
- the expected and observed behavior;
- the potential impact;
- any proof-of-concept material that is safe to share.

Do not access data that does not belong to you, degrade service availability, or disclose a vulnerability before a remediation window has been agreed upon.

## Supported code

Security fixes are applied to the current `main` branch. Older tags and backup branches are retained for history and are not supported production releases.

## Secrets

The repository must never contain production API keys, service-role credentials, signing keys, service-account files, or populated `.env` files. Rotate a credential immediately if it is committed, even if the commit is later removed.
