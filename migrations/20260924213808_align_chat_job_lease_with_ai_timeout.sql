begin;

-- The chat endpoint has a 300-second Vercel ceiling and its image provider may
-- spend up to 240 seconds before local verification, packaging, and durable
-- persistence. Keep the claim lease beyond that complete bounded path so a
-- normal slow reply is not regenerated concurrently.
alter table public.chat_jobs
  add column if not exists claim_token uuid;

alter table public.manuscript_runs
  add column if not exists source_message_id uuid;

create unique index if not exists manuscript_runs_source_message_idx
  on public.manuscript_runs(user_id, source_message_id)
  where source_message_id is not null;

alter table public.usage_events
  add column if not exists idempotency_key text;

create unique index if not exists usage_events_user_type_idempotency_idx
  on public.usage_events(user_id, event_type, idempotency_key)
  where idempotency_key is not null;

-- Included usage must converge just like paid credit spends. Keep the deployed
-- v1 RPC intact for rolling rollback; v2 atomically reports whether this call
-- owns the event, so a replay can never refund the original successful charge.
create or replace function public.consume_usage_event_v2(
  p_user_id uuid,
  p_event_type text,
  p_limit integer,
  p_metadata jsonb default '{}'::jsonb
)
returns table(event_id uuid, used integer, allowed boolean, duplicate boolean)
language plpgsql
security definer
set search_path = ''
as $$
declare
  current_used integer;
  inserted_id uuid;
  existing_id uuid;
  normalized_key text := left(nullif(trim(coalesce(p_metadata->>'usageIdempotencyKey', '')), ''), 160);
begin
  perform pg_advisory_xact_lock(
    pg_catalog.hashtextextended(
      'usage:' || p_user_id::text || ':' || p_event_type,
      0
    )
  );

  if normalized_key is not null then
    select usage.id into existing_id
    from public.usage_events as usage
    where usage.user_id = p_user_id
      and usage.event_type = p_event_type
      and usage.idempotency_key = normalized_key;
  end if;

  select count(*)::integer into current_used
  from public.usage_events as usage
  where usage.user_id = p_user_id
    and usage.event_type = p_event_type
    and usage.created_at >= date_trunc('day', now() at time zone 'utc') at time zone 'utc';

  if existing_id is not null then
    return query select existing_id, current_used, true, true;
    return;
  end if;

  if p_limit >= 0 and current_used >= p_limit then
    return query select null::uuid, current_used, false, false;
    return;
  end if;

  insert into public.usage_events(user_id, event_type, idempotency_key, metadata)
  values (
    p_user_id,
    p_event_type,
    normalized_key,
    coalesce(p_metadata, '{}'::jsonb) - 'usageIdempotencyKey'
  )
  returning id into inserted_id;
  return query select inserted_id, current_used + 1, true, false;
end;
$$;

revoke all on function public.consume_usage_event_v2(uuid, text, integer, jsonb)
  from public, anon, authenticated;
grant execute on function public.consume_usage_event_v2(uuid, text, integer, jsonb)
  to service_role;

-- A fresh quote must not turn a retry of the same durable chat action into a
-- second paid deduction. Keep the v1 action/component contract for unkeyed
-- callers (including distinct manuscript Draft Next steps), while v2 also
-- reconciles an active spend by the explicit usage event type + idempotency
-- key. A refunded spend is not active, so a newly confirmed action can retry;
-- the original refunded approval itself remains non-reusable.
create or replace function public.spend_credits_confirmed_v2(
  p_user_id uuid,
  p_amount integer,
  p_reason text,
  p_action_key text,
  p_component text,
  p_confirmed_max integer,
  p_usage_event_type text,
  p_usage_idempotency_key text,
  p_metadata jsonb default '{}'::jsonb
)
returns table(
  ledger_id uuid,
  balance bigint,
  allowed boolean,
  duplicate boolean,
  limit_exceeded boolean
)
language plpgsql
security definer
set search_path = ''
as $$
declare
  normalized_action text;
  normalized_component text;
  normalized_event_type text;
  normalized_usage_key text;
  external_key text;
  existing public.credit_ledger%rowtype;
  current_balance bigint;
  new_balance bigint;
  inserted_id uuid;
  action_spent bigint;
begin
  if p_user_id is null then
    raise exception 'Credit spend user is required' using errcode = '22023';
  end if;
  if p_amount is null or p_amount <= 0 then
    raise exception 'Credit spend amount must be positive' using errcode = '22023';
  end if;
  if p_confirmed_max is null or p_confirmed_max <= 0
     or p_amount > p_confirmed_max then
    raise exception 'Confirmed credit maximum is invalid' using errcode = '22023';
  end if;

  normalized_action := left(trim(coalesce(p_action_key, '')), 160);
  normalized_component := left(trim(coalesce(p_component, '')), 120);
  normalized_event_type := left(trim(coalesce(p_usage_event_type, '')), 160);
  normalized_usage_key := left(trim(coalesce(p_usage_idempotency_key, '')), 160);
  if normalized_action = '' or normalized_component = '' then
    raise exception 'Confirmed credit action and component are required'
      using errcode = '22023';
  end if;
  if normalized_event_type = '' or normalized_usage_key = '' then
    raise exception 'Usage event type and idempotency key are required'
      using errcode = '22023';
  end if;
  external_key := normalized_action || ':' || normalized_component;

  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended('credits:' || p_user_id::text, 0)
  );

  insert into public.credit_accounts (user_id)
  values (p_user_id)
  on conflict (user_id) do nothing;

  -- Preserve the v1 guarantee that a refunded attempt cannot reuse its old
  -- approval, even when the caller supplies the same durable usage key.
  select ledger.*
  into existing
  from public.credit_ledger as ledger
  where ledger.user_id = p_user_id
    and ledger.provider = 'feature-spend'
    and ledger.external_id = external_key
  limit 1;

  if found then
    select account.balance
    into current_balance
    from public.credit_accounts as account
    where account.user_id = p_user_id;

    if exists (
      select 1
      from public.credit_ledger as refund
      where refund.user_id = p_user_id
        and refund.related_ledger_id = existing.id
        and refund.reason = 'refund'
    ) then
      return query
        select null::uuid, coalesce(current_balance, 0), false, false, true;
      return;
    end if;

    return query
      select existing.id, coalesce(current_balance, 0), true, true, false;
    return;
  end if;

  -- A new quote has a new action key. Reconcile it to an earlier successful,
  -- unrefunded spend for this exact durable usage action before deducting.
  select ledger.*
  into existing
  from public.credit_ledger as ledger
  where ledger.user_id = p_user_id
    and ledger.provider = 'feature-spend'
    and ledger.delta < 0
    and ledger.metadata ->> 'usageEventType' = normalized_event_type
    and ledger.metadata ->> 'usageIdempotencyKey' = normalized_usage_key
    and not exists (
      select 1
      from public.credit_ledger as refund
      where refund.user_id = p_user_id
        and refund.related_ledger_id = ledger.id
        and refund.reason = 'refund'
    )
  order by ledger.created_at desc, ledger.id desc
  limit 1;

  if found then
    select account.balance
    into current_balance
    from public.credit_accounts as account
    where account.user_id = p_user_id;
    return query
      select existing.id, coalesce(current_balance, 0), true, true, false;
    return;
  end if;

  select coalesce(sum(-ledger.delta), 0)
  into action_spent
  from public.credit_ledger as ledger
  where ledger.user_id = p_user_id
    and ledger.provider = 'feature-spend'
    and ledger.delta < 0
    and ledger.metadata ->> 'creditActionKey' = normalized_action;

  if action_spent + p_amount > p_confirmed_max then
    select account.balance
    into current_balance
    from public.credit_accounts as account
    where account.user_id = p_user_id;
    return query
      select null::uuid, coalesce(current_balance, 0), false, false, true;
    return;
  end if;

  select account.balance
  into current_balance
  from public.credit_accounts as account
  where account.user_id = p_user_id
  for update;

  if coalesce(current_balance, 0) < p_amount then
    return query select null::uuid, coalesce(current_balance, 0), false, false, false;
    return;
  end if;

  new_balance := current_balance - p_amount;

  update public.credit_accounts as account
  set balance = new_balance,
      lifetime_spent = account.lifetime_spent + p_amount,
      updated_at = now()
  where account.user_id = p_user_id;

  insert into public.credit_ledger (
    user_id,
    delta,
    balance_after,
    reason,
    provider,
    external_id,
    metadata
  )
  values (
    p_user_id,
    -p_amount,
    new_balance,
    coalesce(nullif(trim(p_reason), ''), 'confirmed_feature_spend'),
    'feature-spend',
    external_key,
    (coalesce(p_metadata, '{}'::jsonb)
      - 'usageEventType'
      - 'usageIdempotencyKey')
      || pg_catalog.jsonb_build_object(
        'creditActionKey', normalized_action,
        'creditComponent', normalized_component,
        'confirmedMaximum', p_confirmed_max,
        'confirmedBoundary', true,
        'usageEventType', normalized_event_type,
        'usageIdempotencyKey', normalized_usage_key
      )
  )
  returning id into inserted_id;

  return query select inserted_id, new_balance, true, false, false;
end;
$$;

revoke all on function public.spend_credits_confirmed_v2(
  uuid, integer, text, text, text, integer, text, text, jsonb
) from public, anon, authenticated;
grant execute on function public.spend_credits_confirmed_v2(
  uuid, integer, text, text, text, integer, text, text, jsonb
) to service_role;

comment on function public.spend_credits_confirmed_v2(
  uuid, integer, text, text, text, integer, text, text, jsonb
) is
  'Service-role-only confirmed deduction reconciled by durable usage action across fresh quotes.';

create or replace function public.claim_chat_job(
  p_user_id uuid,
  p_chat_id uuid,
  p_message_id uuid
)
returns table(job_state text, response_data jsonb)
language plpgsql
security definer
set search_path = public
as $$
declare
  current_job public.chat_jobs%rowtype;
begin
  insert into public.chat_jobs(user_id, chat_id, message_id, status)
  values (p_user_id, p_chat_id, p_message_id, 'processing')
  on conflict (user_id, message_id) do nothing
  returning * into current_job;

  if found then
    return query select 'claimed'::text, null::jsonb;
    return;
  end if;

  select * into current_job
  from public.chat_jobs
  where user_id = p_user_id and message_id = p_message_id
  for update;

  if current_job.status = 'completed' then
    return query select 'completed'::text, current_job.response_data;
    return;
  end if;

  if current_job.status = 'processing'
     and current_job.updated_at > now() - interval '8 minutes' then
    return query select 'busy'::text, null::jsonb;
    return;
  end if;

  update public.chat_jobs
  set status = 'processing', chat_id = p_chat_id, response_data = null,
      error_code = null, claim_token = null, updated_at = now()
  where id = current_job.id;
  return query select 'claimed'::text, null::jsonb;
end;
$$;

revoke all on function public.claim_chat_job(uuid, uuid, uuid) from public;
grant execute on function public.claim_chat_job(uuid, uuid, uuid) to service_role;

-- New callers receive an ownership token. Every state transition made by that
-- worker is fenced by this token, so a stale process cannot release or finish a
-- newer worker's claim.
create or replace function public.claim_chat_job_v2(
  p_user_id uuid,
  p_chat_id uuid,
  p_message_id uuid
)
returns table(job_state text, response_data jsonb, claim_token uuid)
language plpgsql
security definer
set search_path = public
as $$
declare
  current_job public.chat_jobs%rowtype;
  next_claim_token uuid := gen_random_uuid();
begin
  insert into public.chat_jobs(user_id, chat_id, message_id, status, claim_token)
  values (p_user_id, p_chat_id, p_message_id, 'processing', next_claim_token)
  on conflict (user_id, message_id) do nothing
  returning * into current_job;

  if found then
    return query select 'claimed'::text, null::jsonb, current_job.claim_token;
    return;
  end if;

  select * into current_job
  from public.chat_jobs
  where user_id = p_user_id and message_id = p_message_id
  for update;

  if current_job.status = 'completed' then
    return query select 'completed'::text, current_job.response_data, null::uuid;
    return;
  end if;

  if current_job.status = 'processing'
     and current_job.updated_at > now() - interval '8 minutes' then
    return query select 'busy'::text, null::jsonb, null::uuid;
    return;
  end if;

  update public.chat_jobs
  set status = 'processing', chat_id = p_chat_id, response_data = null,
      error_code = null, claim_token = next_claim_token, updated_at = now()
  where id = current_job.id
  returning * into current_job;
  return query select 'claimed'::text, null::jsonb, current_job.claim_token;
end;
$$;

revoke all on function public.claim_chat_job_v2(uuid, uuid, uuid)
  from public, anon, authenticated;
grant execute on function public.claim_chat_job_v2(uuid, uuid, uuid)
  to service_role;

create or replace function public.release_chat_job_claim(
  p_user_id uuid,
  p_message_id uuid,
  p_claim_token uuid,
  p_error_code text default 'REPLY_RECONCILIATION_UNAVAILABLE'
)
returns boolean
language plpgsql
security definer
set search_path = public
as $$
begin
  update public.chat_jobs
  set status = 'failed',
      error_code = left(coalesce(nullif(p_error_code, ''), 'REPLY_RECONCILIATION_UNAVAILABLE'), 160),
      claim_token = null,
      updated_at = now()
  where user_id = p_user_id
    and message_id = p_message_id
    and status = 'processing'
    and claim_token = p_claim_token;
  return found;
end;
$$;

revoke all on function public.release_chat_job_claim(uuid, uuid, uuid, text)
  from public, anon, authenticated;
grant execute on function public.release_chat_job_claim(uuid, uuid, uuid, text)
  to service_role;

-- A chat-initiated manuscript is one paid durable handoff, not four unrelated
-- writes. Lock the owned chat claim, reconcile by source message, and create
-- Project + mapping + Manuscript + Run in this single database transaction.
create or replace function public.begin_chat_manuscript_workspace(
  p_user_id uuid,
  p_chat_id uuid,
  p_source_message_id uuid,
  p_claim_token uuid,
  p_project_id uuid,
  p_project_limit integer,
  p_project_name text,
  p_project_description text,
  p_project_instructions text,
  p_manuscript_title text,
  p_author_name text,
  p_brief text,
  p_target_words integer,
  p_chapter_count integer,
  p_preferred_export_format text,
  p_blueprint_receipt jsonb,
  p_approved_credit_limit integer,
  p_planned_chargeable_steps integer,
  p_credit_action_key text
)
returns table(
  project_row jsonb,
  manuscript_row jsonb,
  run_row jsonb,
  project_created boolean,
  reconciled boolean
)
language plpgsql
security definer
set search_path = ''
as $$
declare
  selected_project public.projects%rowtype;
  selected_manuscript public.manuscripts%rowtype;
  selected_run public.manuscript_runs%rowtype;
  active_project_count integer := 0;
  created_project boolean := false;
  normalized_format text := lower(trim(coalesce(p_preferred_export_format, 'docx')));
  normalized_chapters integer := greatest(8, least(80, coalesce(p_chapter_count, 28)));
  normalized_target_words integer := greatest(20000, least(150000, coalesce(p_target_words, 80000)));
begin
  if p_user_id is null or p_chat_id is null or p_source_message_id is null
     or p_claim_token is null then
    raise exception 'manuscript handoff identity is required' using errcode = '22023';
  end if;

  if normalized_format not in ('docx', 'pdf', 'epub') then
    normalized_format := 'docx';
  end if;

  perform 1
  from public.chat_jobs as job
  where job.user_id = p_user_id
    and job.chat_id = p_chat_id
    and job.message_id = p_source_message_id
    and job.status = 'processing'
    and job.claim_token = p_claim_token
  for update;
  if not found then
    raise exception 'owned manuscript chat claim is unavailable' using errcode = '55000';
  end if;

  select * into selected_run
  from public.manuscript_runs as existing_run
  where existing_run.user_id = p_user_id
    and existing_run.source_message_id = p_source_message_id;

  if found then
    select * into selected_project
    from public.projects as existing_project
    where existing_project.id = selected_run.project_id
      and existing_project.user_id = p_user_id;
    select * into selected_manuscript
    from public.manuscripts as existing_manuscript
    where existing_manuscript.id = selected_run.manuscript_id
      and existing_manuscript.user_id = p_user_id;
    if selected_project.id is null or selected_manuscript.id is null then
      raise exception 'reconciled manuscript workspace is incomplete' using errcode = '55000';
    end if;
    return query select
      to_jsonb(selected_project),
      to_jsonb(selected_manuscript),
      to_jsonb(selected_run),
      false,
      true;
    return;
  end if;

  if p_project_id is not null then
    select * into selected_project
    from public.projects as owned_project
    where owned_project.id = p_project_id
      and owned_project.user_id = p_user_id
      and owned_project.archived_at is null
    for update;
    if not found then
      raise exception 'project not found' using errcode = 'P0002';
    end if;
  else
    if coalesce(p_project_limit, 0) >= 0 then
      select count(*) into active_project_count
      from public.projects as counted_project
      where counted_project.user_id = p_user_id
        and counted_project.archived_at is null;
      if active_project_count >= p_project_limit then
        raise exception 'project limit reached' using errcode = 'P0001';
      end if;
    end if;

    insert into public.projects(
      user_id, name, description, instructions, metadata, updated_at
    ) values (
      p_user_id,
      left(coalesce(nullif(trim(p_project_name), ''), 'Untitled Manuscript'), 100),
      left(coalesce(p_project_description, ''), 1200),
      left(coalesce(p_project_instructions, ''), 10000),
      jsonb_build_object('source', 'chat_long_form_handoff'),
      now()
    ) returning * into selected_project;
    created_project := true;
  end if;

  insert into public.manuscripts(
    user_id, project_id, title, subtitle, author_name,
    trim_code, trim_width, trim_height, bleed, status, metadata, updated_at
  ) values (
    p_user_id,
    selected_project.id,
    left(coalesce(nullif(trim(p_manuscript_title), ''), 'Untitled Manuscript'), 180),
    '',
    left(coalesce(p_author_name, ''), 160),
    '6x9', 6.0, 9.0, false, 'draft',
    jsonb_build_object(
      'preferredExportFormat', normalized_format,
      'source', 'chat_long_form_handoff',
      'premise', left(coalesce(p_brief, ''), 1200),
      'targetWords', normalized_target_words,
      'plannedChapterCount', normalized_chapters
    ),
    now()
  ) returning * into selected_manuscript;

  insert into public.project_chats(project_id, user_id, chat_id)
  values (selected_project.id, p_user_id, p_chat_id)
  on conflict (project_id, chat_id) do nothing;

  update public.projects
  set updated_at = now()
  where id = selected_project.id and user_id = p_user_id
  returning * into selected_project;

  insert into public.manuscript_runs(
    user_id, project_id, manuscript_id, chat_id, source_message_id,
    status, stage, mode, brief, target_words, chapter_count,
    preferred_export_format, completed_sections, total_sections,
    not_before, blueprint_receipt, approved_credit_limit, credits_spent,
    planned_steps, planned_chargeable_steps, credit_per_step,
    credit_action_key, metadata, updated_at
  ) values (
    p_user_id,
    selected_project.id,
    selected_manuscript.id,
    p_chat_id,
    p_source_message_id,
    'queued', 'blueprint', 'autopilot', left(coalesce(p_brief, ''), 12000),
    normalized_target_words, normalized_chapters, normalized_format,
    0, 0, now(), coalesce(p_blueprint_receipt, '{}'::jsonb),
    greatest(0, coalesce(p_approved_credit_limit, 0)), 0,
    normalized_chapters,
    least(normalized_chapters, greatest(0, coalesce(p_planned_chargeable_steps, 0))),
    8, left(coalesce(p_credit_action_key, ''), 160),
    jsonb_build_object('source', 'chat_long_form_handoff'), now()
  ) returning * into selected_run;

  return query select
    to_jsonb(selected_project),
    to_jsonb(selected_manuscript),
    to_jsonb(selected_run),
    created_project,
    false;
end;
$$;

revoke all on function public.begin_chat_manuscript_workspace(
  uuid, uuid, uuid, uuid, uuid, integer, text, text, text, text,
  text, text, integer, integer, text, jsonb, integer, integer, text
) from public, anon, authenticated;
grant execute on function public.begin_chat_manuscript_workspace(
  uuid, uuid, uuid, uuid, uuid, integer, text, text, text, text,
  text, text, integer, integer, text, jsonb, integer, integer, text
) to service_role;

comment on function public.begin_chat_manuscript_workspace(
  uuid, uuid, uuid, uuid, uuid, integer, text, text, text, text,
  text, text, integer, integer, text, jsonb, integer, integer, text
) is 'Atomically creates or reconciles one chat manuscript workspace per user message.';

-- A reply stores the immutable, fingerprint-derived version id. Only after that
-- reply is durable do we hide older versions of the same logical message output.
create or replace function public.retire_generated_document_versions(
  p_user_id uuid,
  p_logical_file_id uuid,
  p_keep_file_id uuid
)
returns integer
language plpgsql
security definer
set search_path = public
as $$
declare
  keep_row public.user_files%rowtype;
  retired_count integer := 0;
begin
  select * into keep_row
  from public.user_files
  where id = p_keep_file_id
    and user_id = p_user_id
    and kind = 'generated_document'
  for update;

  if not found then
    raise exception 'generated document version not found';
  end if;
  if coalesce(keep_row.metadata->>'_logicalArtifactId', '') <> p_logical_file_id::text then
    raise exception 'generated document logical identity mismatch';
  end if;

  update public.user_files
  set deleted_at = now(), updated_at = now()
  where user_id = p_user_id
    and kind = 'generated_document'
    and id <> p_keep_file_id
    and deleted_at is null
    and (
      id = p_logical_file_id
      or metadata->>'_logicalArtifactId' = p_logical_file_id::text
    );
  get diagnostics retired_count = row_count;

  update public.user_files
  set deleted_at = null, updated_at = now()
  where id = p_keep_file_id and user_id = p_user_id;

  return retired_count;
end;
$$;

revoke all on function public.retire_generated_document_versions(uuid, uuid, uuid)
  from public, anon, authenticated;
grant execute on function public.retire_generated_document_versions(uuid, uuid, uuid)
  to service_role;

commit;
