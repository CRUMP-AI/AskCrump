# AI Safety Report Moderation Runbook

Ask Crump provides an in-app **Report** action beneath every assistant response. Reports enter `public.ai_content_reports`, which is intentionally inaccessible to anonymous and ordinary authenticated Data API roles. Only trusted backend/admin service-role workflows may access the queue.

## Launch operating cadence

- Review the queue at least daily during internal testing, store review, and initial launch.
- Move every reviewed item from `new` to `reviewing`, then to `resolved` or `dismissed` with a short factual resolution note.
- Never copy reported user content into unsecured chat, email, screenshots, or personal notes.
- Restrict moderator access to named company administrators with multifactor authentication.

## Triage order

1. Credible imminent harm, self-harm, child safety, or violent threats
2. Privacy exposure, credentials, financial fraud, or targeted harassment
3. Dangerous instructions, hate, sexual content, or deceptive output
4. Copyright and other quality/policy concerns

For suspected illegal material or an imminent safety emergency, do not investigate casually or redistribute content. Preserve minimum necessary records, restrict access, and follow qualified legal/emergency guidance appropriate to the jurisdiction.

## Review query

Run only through a trusted administrative SQL session:

```sql
select
  id,
  category,
  status,
  created_at,
  user_id,
  chat_id,
  message_id,
  comment,
  prompt_context,
  reported_output
from public.ai_content_reports
where status in ('new', 'reviewing')
order by
  case category
    when 'self_harm' then 1
    when 'violence_or_danger' then 2
    when 'privacy' then 3
    when 'deception_or_fraud' then 4
    else 5
  end,
  created_at asc;
```

## Update a report

```sql
update public.ai_content_reports
set
  status = 'resolved',
  resolution_notes = 'Concise factual action taken; do not add unrelated personal data.',
  updated_at = now()
where id = '<report-id>';
```

Use `dismissed` only when the report does not identify a policy or safety issue. A disagreement with the user is not enough reason to erase the report.

## Possible corrective actions

- add or tune an input/output safeguard
- block a dangerous workflow or provider fallback
- improve system instructions or tool authorization
- correct misleading product copy or safety guidance
- report a provider-level defect through the provider's secure channel
- suspend an abusive account only after documented, consistent review
- notify affected users when appropriate and legally permitted

Track recurring categories and root causes without turning report content into advertising profiles. The queue is deleted with the owning account through the database foreign-key cascade; any legally required exception must be documented separately in the privacy/retention program.

## Weekly launch review

- number of reports by category and model/provider
- median time to first review and resolution
- repeated failure pattern or prompt family
- safeguard change made and regression test added
- false-positive/dismissal rate
- unresolved high-priority items

Google Play's generative-AI policy requires in-app reporting/flagging and expects reports to inform content moderation. Recheck the current policy before every store release: <https://support.google.com/googleplay/android-developer/answer/13985936>
