-- Ask Crump v4: Python backend, durable sessions, atomic cross-device sync.
-- Run once in the Supabase SQL editor before deploying v4.
-- This migration intentionally invalidates insecure pre-v4 raw-token sessions,
-- so every existing user signs in once after deployment and then receives a
-- sliding 365-day session.

begin;
create extension if not exists pgcrypto;

create table if not exists public.users (
  id uuid primary key default gen_random_uuid(),
  email text not null,
  password_hash text not null,
  full_name text,
  profile_picture text,
  is_verified boolean not null default false,
  preferences jsonb not null default '{}'::jsonb,
  subscription_tier text not null default 'free',
  subscription_status text not null default 'inactive',
  subscription_provider text,
  stripe_customer_id text,
  stripe_subscription_id text,
  store_product_id text,
  subscription_current_period_end timestamptz,
  trial_end timestamptz,
  verification_token_hash text,
  verification_token_expires timestamptz,
  password_reset_token_hash text,
  password_reset_expires timestamptz,
  last_login timestamptz,
  terms_accepted_at timestamptz,
  terms_version text,
  deleted_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.users add column if not exists profile_picture text;
alter table public.users add column if not exists preferences jsonb not null default '{}'::jsonb;
alter table public.users add column if not exists subscription_tier text not null default 'free';
alter table public.users add column if not exists subscription_status text not null default 'inactive';
alter table public.users add column if not exists subscription_provider text;
alter table public.users add column if not exists stripe_customer_id text;
alter table public.users add column if not exists stripe_subscription_id text;
alter table public.users add column if not exists store_product_id text;
alter table public.users add column if not exists subscription_current_period_end timestamptz;
alter table public.users add column if not exists trial_end timestamptz;
alter table public.users add column if not exists verification_token_hash text;
alter table public.users add column if not exists verification_token_expires timestamptz;
alter table public.users add column if not exists password_reset_token_hash text;
alter table public.users add column if not exists password_reset_expires timestamptz;
alter table public.users add column if not exists last_login timestamptz;
alter table public.users add column if not exists terms_accepted_at timestamptz;
alter table public.users add column if not exists terms_version text;
alter table public.users add column if not exists deleted_at timestamptz;
alter table public.users add column if not exists created_at timestamptz not null default now();
alter table public.users add column if not exists updated_at timestamptz not null default now();

do $$
begin
  if exists (select 1 from public.users where email is null or btrim(email) = '') then
    raise exception 'Ask Crump migration stopped: one or more users have a missing email address.';
  end if;
  if exists (select 1 from public.users where password_hash is null or btrim(password_hash) = '') then
    raise exception 'Ask Crump migration stopped: one or more users have a missing password hash.';
  end if;
  if exists (
    select 1
    from public.users
    group by lower(btrim(email))
    having count(*) > 1
  ) then
    raise exception 'Ask Crump migration stopped: duplicate user emails exist after case normalization. Merge those accounts before retrying.';
  end if;
end $$;

update public.users set email = lower(btrim(email)) where email <> lower(btrim(email));
alter table public.users alter column email set not null;
alter table public.users alter column password_hash set not null;
create unique index if not exists users_email_lower_unique on public.users (lower(email));
create index if not exists users_stripe_customer_idx on public.users (stripe_customer_id);

create table if not exists public.sessions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  token_hash text not null,
  device_id text,
  device_name text,
  platform text,
  device_info jsonb not null default '{}'::jsonb,
  ip_address text,
  user_agent text,
  created_at timestamptz not null default now(),
  last_activity timestamptz not null default now(),
  expires_at timestamptz not null,
  revoked_at timestamptz
);
alter table public.sessions add column if not exists token_hash text;
alter table public.sessions add column if not exists device_id text;
alter table public.sessions add column if not exists device_name text;
alter table public.sessions add column if not exists platform text;
alter table public.sessions add column if not exists device_info jsonb not null default '{}'::jsonb;
alter table public.sessions add column if not exists ip_address text;
alter table public.sessions add column if not exists user_agent text;
alter table public.sessions add column if not exists created_at timestamptz not null default now();
alter table public.sessions add column if not exists last_activity timestamptz not null default now();
alter table public.sessions add column if not exists revoked_at timestamptz;
alter table public.sessions add column if not exists expires_at timestamptz;

-- Pre-v4 sessions used raw credentials and are deliberately not trusted.
delete from public.sessions where token_hash is null;
alter table public.sessions drop column if exists session_token;
alter table public.sessions alter column token_hash set not null;
update public.sessions set expires_at = now() + interval '365 days' where expires_at is null;
delete from public.sessions where user_id is null;
alter table public.sessions alter column user_id set not null;
alter table public.sessions alter column expires_at set not null;
create unique index if not exists sessions_token_hash_unique on public.sessions(token_hash);
create index if not exists sessions_user_active_idx on public.sessions(user_id, last_activity desc) where revoked_at is null;
create index if not exists sessions_expiry_idx on public.sessions(expires_at);

create table if not exists public.user_chats (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  chat_id uuid not null,
  title text not null default 'New conversation',
  messages jsonb not null default '[]'::jsonb,
  revision bigint not null default 1,
  deleted_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(user_id, chat_id)
);
alter table public.user_chats add column if not exists user_id uuid references public.users(id) on delete cascade;
alter table public.user_chats add column if not exists chat_id uuid;
alter table public.user_chats add column if not exists title text not null default 'New conversation';
alter table public.user_chats add column if not exists messages jsonb not null default '[]'::jsonb;
alter table public.user_chats add column if not exists revision bigint not null default 1;
alter table public.user_chats add column if not exists deleted_at timestamptz;
alter table public.user_chats add column if not exists created_at timestamptz not null default now();
alter table public.user_chats add column if not exists updated_at timestamptz not null default now();

-- Canonicalize every legacy chat identifier to UUID without losing stable identity.
do $$
declare
  chat_id_type text;
begin
  select data_type into chat_id_type
  from information_schema.columns
  where table_schema = 'public' and table_name = 'user_chats' and column_name = 'chat_id';

  if chat_id_type = 'uuid' then
    update public.user_chats set chat_id = id where chat_id is null;
  else
    execute $convert$
      alter table public.user_chats
      alter column chat_id type uuid
      using (
        case
          when chat_id is null then id
          when chat_id::text ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
            then chat_id::text::uuid
          else (
            substr(md5('askcrump:chat:' || chat_id::text),1,8) || '-' ||
            substr(md5('askcrump:chat:' || chat_id::text),9,4) || '-5' ||
            substr(md5('askcrump:chat:' || chat_id::text),14,3) || '-a' ||
            substr(md5('askcrump:chat:' || chat_id::text),18,3) || '-' ||
            substr(md5('askcrump:chat:' || chat_id::text),21,12)
          )::uuid
        end
      )
    $convert$;
  end if;
end $$;

delete from public.user_chats where user_id is null or chat_id is null;
with ranked as (
  select ctid, row_number() over (
    partition by user_id, chat_id
    order by updated_at desc nulls last, revision desc nulls last, id desc
  ) as position
  from public.user_chats
)
delete from public.user_chats target
using ranked
where target.ctid = ranked.ctid and ranked.position > 1;

alter table public.user_chats alter column user_id set not null;
alter table public.user_chats alter column chat_id set not null;
alter table public.user_chats alter column messages set default '[]'::jsonb;
update public.user_chats set messages = '[]'::jsonb where messages is null;
alter table public.user_chats alter column messages set not null;
create unique index if not exists user_chats_user_chat_unique on public.user_chats(user_id, chat_id);
create index if not exists user_chats_sync_idx on public.user_chats(user_id, updated_at);

create table if not exists public.user_settings (
  user_id uuid primary key references public.users(id) on delete cascade,
  assistant_name text default 'Crump',
  work_mode boolean not null default false,
  work_start integer not null default 9,
  work_end integer not null default 17,
  preferences jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
alter table public.user_settings add column if not exists user_id uuid references public.users(id) on delete cascade;
alter table public.user_settings add column if not exists assistant_name text default 'Crump';
alter table public.user_settings add column if not exists work_mode boolean not null default false;
alter table public.user_settings add column if not exists work_start integer not null default 9;
alter table public.user_settings add column if not exists work_end integer not null default 17;
alter table public.user_settings add column if not exists preferences jsonb not null default '{}'::jsonb;
alter table public.user_settings add column if not exists created_at timestamptz not null default now();
alter table public.user_settings add column if not exists updated_at timestamptz not null default now();


delete from public.user_settings where user_id is null;
with ranked as (
  select ctid, row_number() over (
    partition by user_id
    order by updated_at desc nulls last, created_at desc nulls last
  ) as position
  from public.user_settings
)
delete from public.user_settings target
using ranked
where target.ctid = ranked.ctid and ranked.position > 1;
alter table public.user_settings alter column user_id set not null;
create unique index if not exists user_settings_user_unique on public.user_settings(user_id);
insert into public.user_settings (user_id)
select users.id from public.users users
where not exists (select 1 from public.user_settings settings where settings.user_id = users.id);

create table if not exists public.usage_events (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  event_type text not null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create index if not exists usage_events_daily_idx on public.usage_events(user_id, event_type, created_at desc);

create table if not exists public.rate_limit_events (
  id uuid primary key default gen_random_uuid(),
  scope text not null,
  key_hash text not null,
  created_at timestamptz not null default now()
);
create index if not exists rate_limit_events_lookup_idx on public.rate_limit_events(scope, key_hash, created_at desc);

create or replace function public.consume_usage_event(
  p_user_id uuid,
  p_event_type text,
  p_limit integer,
  p_metadata jsonb default '{}'::jsonb
)
returns table(event_id uuid, used integer, allowed boolean)
language plpgsql
security definer
set search_path = public
as $$
declare
  current_used integer;
  inserted_id uuid;
begin
  perform pg_advisory_xact_lock(hashtextextended(p_user_id::text || ':' || p_event_type || ':' || current_date::text, 0));
  select count(*)::integer into current_used
  from public.usage_events
  where user_id = p_user_id
    and event_type = p_event_type
    and created_at >= date_trunc('day', now() at time zone 'utc') at time zone 'utc';

  if p_limit >= 0 and current_used >= p_limit then
    return query select null::uuid, current_used, false;
    return;
  end if;

  insert into public.usage_events (user_id, event_type, metadata)
  values (p_user_id, p_event_type, coalesce(p_metadata, '{}'::jsonb))
  returning id into inserted_id;
  return query select inserted_id, current_used + 1, true;
end;
$$;

create or replace function public.consume_rate_limit_event(
  p_scope text,
  p_key_hash text,
  p_limit integer,
  p_window_seconds integer
)
returns table(used integer, allowed boolean, retry_after integer)
language plpgsql
security definer
set search_path = public
as $$
declare
  current_used integer;
  oldest_event timestamptz;
  retry_seconds integer;
begin
  if p_limit < 1 or p_window_seconds < 1 then
    raise exception 'Invalid rate-limit configuration';
  end if;

  perform pg_advisory_xact_lock(hashtextextended(p_scope || ':' || p_key_hash, 0));
  delete from public.rate_limit_events
  where scope = p_scope
    and key_hash = p_key_hash
    and created_at < now() - make_interval(secs => p_window_seconds * 2);

  select count(*)::integer, min(created_at)
    into current_used, oldest_event
  from public.rate_limit_events
  where scope = p_scope
    and key_hash = p_key_hash
    and created_at >= now() - make_interval(secs => p_window_seconds);

  if current_used >= p_limit then
    retry_seconds := greatest(1, ceil(p_window_seconds - extract(epoch from (now() - oldest_event)))::integer);
    return query select current_used, false, retry_seconds;
    return;
  end if;

  insert into public.rate_limit_events(scope, key_hash) values (p_scope, p_key_hash);
  return query select current_used + 1, true, 0;
end;
$$;

-- Atomic compare-and-apply prevents simultaneous devices from racing between a
-- SELECT and an UPSERT. Newer timestamps win; revision breaks exact ties.
create or replace function public.apply_chat_sync(
  p_user_id uuid,
  p_chat_id uuid,
  p_title text,
  p_messages jsonb,
  p_created_at timestamptz,
  p_updated_at timestamptz,
  p_deleted_at timestamptz,
  p_revision bigint
)
returns table(accepted boolean, resulting_revision bigint)
language plpgsql
security definer
set search_path = public
as $$
declare
  applied_revision bigint;
begin
  insert into public.user_chats as current_chat (
    user_id, chat_id, title, messages, created_at, updated_at, deleted_at, revision
  ) values (
    p_user_id,
    p_chat_id,
    coalesce(nullif(p_title, ''), 'New conversation'),
    coalesce(p_messages, '[]'::jsonb),
    coalesce(p_created_at, p_updated_at, now()),
    coalesce(p_updated_at, now()),
    p_deleted_at,
    greatest(1, coalesce(p_revision, 1))
  )
  on conflict (user_id, chat_id) do update
  set title = excluded.title,
      messages = excluded.messages,
      deleted_at = excluded.deleted_at,
      created_at = least(current_chat.created_at, excluded.created_at),
      updated_at = excluded.updated_at,
      revision = greatest(excluded.revision, current_chat.revision + 1)
  where excluded.updated_at > current_chat.updated_at
     or (excluded.updated_at = current_chat.updated_at and excluded.revision > current_chat.revision)
  returning current_chat.revision into applied_revision;

  if found then
    return query select true, applied_revision;
  else
    select revision into applied_revision
    from public.user_chats
    where user_id = p_user_id and chat_id = p_chat_id;
    return query select false, coalesce(applied_revision, 1);
  end if;
end;
$$;


create or replace function public.delete_user_account(p_user_id uuid)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  if to_regclass('public.crump_chats') is not null then
    execute 'delete from public.crump_chats where user_id = $1' using p_user_id;
  end if;
  if to_regclass('public.devices') is not null then
    execute 'delete from public.devices where user_id = $1' using p_user_id;
  end if;
  delete from public.usage_events where user_id = p_user_id;
  delete from public.user_chats where user_id = p_user_id;
  delete from public.user_settings where user_id = p_user_id;
  delete from public.sessions where user_id = p_user_id;
  delete from public.users where id = p_user_id;
end;
$$;

revoke all on function public.consume_usage_event(uuid, text, integer, jsonb) from public;
revoke all on function public.consume_rate_limit_event(text, text, integer, integer) from public;
revoke all on function public.apply_chat_sync(uuid, uuid, text, jsonb, timestamptz, timestamptz, timestamptz, bigint) from public;
revoke all on function public.delete_user_account(uuid) from public;
grant execute on function public.consume_usage_event(uuid, text, integer, jsonb) to service_role;
grant execute on function public.consume_rate_limit_event(text, text, integer, integer) to service_role;
grant execute on function public.apply_chat_sync(uuid, uuid, text, jsonb, timestamptz, timestamptz, timestamptz, bigint) to service_role;
grant execute on function public.delete_user_account(uuid) to service_role;

-- Move records from the older duplicate table when it exists. Duplicate source
-- rows are collapsed deterministically before insertion.
do $$
begin
  if to_regclass('public.crump_chats') is not null then
    execute $migration$
      with source as (
        select
          user_id,
          case
            when chat_id::text ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
              then chat_id::text::uuid
            else (
              substr(md5('askcrump:chat:' || chat_id::text),1,8) || '-' ||
              substr(md5('askcrump:chat:' || chat_id::text),9,4) || '-5' ||
              substr(md5('askcrump:chat:' || chat_id::text),14,3) || '-a' ||
              substr(md5('askcrump:chat:' || chat_id::text),18,3) || '-' ||
              substr(md5('askcrump:chat:' || chat_id::text),21,12)
            )::uuid
          end as normalized_chat_id,
          coalesce(title, 'New conversation') as title,
          coalesce(messages, '[]'::jsonb) as messages,
          coalesce(created_at, now()) as created_at,
          coalesce(updated_at, created_at, now()) as updated_at
        from public.crump_chats
        where user_id is not null and chat_id is not null
      ), deduped as (
        select distinct on (user_id, normalized_chat_id) *
        from source
        order by user_id, normalized_chat_id, updated_at desc
      )
      insert into public.user_chats (user_id, chat_id, title, messages, created_at, updated_at)
      select user_id, normalized_chat_id, title, messages, created_at, updated_at
      from deduped
      on conflict (user_id, chat_id) do update
      set title = excluded.title,
          messages = excluded.messages,
          updated_at = greatest(public.user_chats.updated_at, excluded.updated_at)
    $migration$;
  end if;
exception when others then
  raise exception 'Legacy crump_chats migration failed: %', sqlerrm;
end $$;

-- The browser and native clients never receive a Supabase key. The Python API
-- uses service-role access; all direct public table access is denied by RLS.
alter table public.users enable row level security;
alter table public.sessions enable row level security;
alter table public.user_chats enable row level security;
alter table public.user_settings enable row level security;
do $$
begin
  if to_regclass('public.devices') is not null then
    alter table public.devices enable row level security;
  end if;
end $$;
alter table public.usage_events enable row level security;
alter table public.rate_limit_events enable row level security;

do $$
begin
  if to_regclass('public.crump_chats') is not null then
    alter table public.crump_chats enable row level security;
  end if;
end $$;

-- Message presence, native push, and server-side Crump Check-ins.
create table if not exists public.message_receipts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  chat_id uuid not null,
  message_id uuid not null,
  delivered_at timestamptz not null default now(),
  seen_at timestamptz,
  activity text not null default 'thinking',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(user_id, message_id)
);
create index if not exists message_receipts_chat_idx on public.message_receipts(user_id, chat_id, created_at desc);

create table if not exists public.chat_jobs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  chat_id uuid not null,
  message_id uuid not null,
  status text not null default 'processing',
  response_data jsonb,
  error_code text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(user_id, message_id)
);
create index if not exists chat_jobs_lookup_idx on public.chat_jobs(user_id, message_id, updated_at desc);

create table if not exists public.push_tokens (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  installation_id text not null,
  platform text not null check (platform in ('ios', 'android')),
  token text not null,
  enabled boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  last_used_at timestamptz,
  unique(user_id, installation_id),
  unique(token)
);
create index if not exists push_tokens_user_idx on public.push_tokens(user_id, enabled);

create table if not exists public.check_in_preferences (
  user_id uuid primary key references public.users(id) on delete cascade,
  enabled boolean not null default false,
  frequency text not null default 'balanced' check (frequency in ('occasional', 'balanced', 'active')),
  quiet_start integer not null default 21 check (quiet_start between 0 and 23),
  quiet_end integer not null default 8 check (quiet_end between 0 and 23),
  timezone text not null default 'America/New_York',
  notifications_enabled boolean not null default false,
  haptics_enabled boolean not null default true,
  allow_followups boolean not null default true,
  allow_reminders boolean not null default true,
  allow_goals boolean not null default true,
  allow_encouragement boolean not null default false,
  ignored_count integer not null default 0,
  last_check_in_at timestamptz,
  next_eligible_at timestamptz not null default now() + interval '36 hours',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
insert into public.check_in_preferences (user_id)
select users.id from public.users users
where not exists (select 1 from public.check_in_preferences prefs where prefs.user_id = users.id);
create index if not exists check_in_preferences_due_idx on public.check_in_preferences(enabled, next_eligible_at);

create table if not exists public.check_in_events (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  chat_id uuid not null,
  message_id uuid not null,
  reason text not null,
  content text not null,
  status text not null default 'sent' check (status in ('sent', 'responded', 'ignored', 'cancelled')),
  sent_at timestamptz not null default now(),
  responded_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists check_in_events_status_idx on public.check_in_events(user_id, status, sent_at desc);

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
     and current_job.updated_at > now() - interval '2 minutes' then
    return query select 'busy'::text, null::jsonb;
    return;
  end if;

  update public.chat_jobs
  set status = 'processing', chat_id = p_chat_id, response_data = null,
      error_code = null, updated_at = now()
  where id = current_job.id;
  return query select 'claimed'::text, null::jsonb;
end;
$$;

create or replace function public.append_check_in_message(
  p_user_id uuid,
  p_chat_id uuid,
  p_message jsonb
)
returns table(appended boolean, resulting_revision bigint)
language plpgsql
security definer
set search_path = public
as $$
declare
  current_revision bigint;
begin
  update public.user_chats
  set messages = coalesce(messages, '[]'::jsonb) || jsonb_build_array(p_message),
      updated_at = now(),
      revision = revision + 1
  where user_id = p_user_id
    and chat_id = p_chat_id
    and deleted_at is null
  returning revision into current_revision;

  if found then
    return query select true, current_revision;
  else
    return query select false, 0::bigint;
  end if;
end;
$$;

alter table public.message_receipts enable row level security;
alter table public.chat_jobs enable row level security;
alter table public.push_tokens enable row level security;
alter table public.check_in_preferences enable row level security;
alter table public.check_in_events enable row level security;

revoke all on function public.claim_chat_job(uuid, uuid, uuid) from public;
revoke all on function public.append_check_in_message(uuid, uuid, jsonb) from public;
grant execute on function public.claim_chat_job(uuid, uuid, uuid) to service_role;
grant execute on function public.append_check_in_message(uuid, uuid, jsonb) to service_role;

commit;
