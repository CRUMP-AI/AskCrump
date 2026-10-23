-- Ask Crump registered-account cohort correction.
-- Guest preview rows exist before registration. Keep their identity/history while
-- giving every accepted registration one durable, immutable cohort timestamp.

begin;

set local lock_timeout = '5s';
set local statement_timeout = '30s';

alter table public.users
  add column if not exists registration_submitted_at timestamptz;

comment on column public.users.registration_submitted_at is
  'First server-accepted registration submission. Null for preview-only guests and unmarked legacy accounts; immutable after first population.';

-- Guest access first became available at this verified production boundary.
-- A non-guest, or a guest whose placeholder email has already been replaced,
-- created at or after that instant without positive registration evidence is
-- ambiguous: it might be a submitted registration whose best-effort
-- AccountCreated event failed. Refuse the migration instead of assigning the
-- original preview timestamp to a registered-user cohort or stranding a later
-- verification behind the cohort constraint.
do $migration$
declare
  v_ambiguous_accounts bigint;
begin
  select pg_catalog.count(*)
    into v_ambiguous_accounts
    from public.users as account
   where account.registration_submitted_at is null
     and account.created_at >= timestamptz '2026-10-23 18:01:51.842574+00'
     and (
       account.is_guest is false
       or account.email is null
       or pg_catalog.lower(pg_catalog.btrim(account.email)) <>
         'guest-' || account.id::text || '@guest.askcrump.local'
     )
     and not exists (
       select 1
       from public.product_events as event
       where event.user_id = account.id
         and event.event_name = 'AccountCreated'
         and event.environment in ('production', 'preview', 'development')
         and event.created_at >= account.created_at
     );

  if v_ambiguous_accounts > 0 then
    raise exception
      'Found % ambiguous post-guest-launch account(s); refusing cohort migration.',
      v_ambiguous_accounts
      using errcode = '55000';
  end if;
end
$migration$;

-- Product events remain best-effort for new traffic, but a historical
-- AccountCreated row is positive evidence that an older account submitted
-- registration. Use only the earliest valid event and never infer from a
-- mutable updated_at value.
with first_account_created as (
  select distinct on (event.user_id)
    event.user_id,
    event.created_at,
    event.environment
  from public.product_events as event
  join public.users as account
    on account.id = event.user_id
  where event.event_name = 'AccountCreated'
    and event.environment in ('production', 'preview', 'development')
    and account.created_at is not null
    and event.created_at >= account.created_at
  order by event.user_id, event.created_at, event.id
)
update public.users as account
   set registration_submitted_at = first_event.created_at,
       registration_environment = first_event.environment
  from first_account_created as first_event
 where account.id = first_event.user_id
   and account.registration_submitted_at is null
   and account.created_at is not null
   and first_event.created_at >= account.created_at;

do $migration$
begin
  if not exists (
    select 1
    from pg_catalog.pg_constraint as constraint_row
    where constraint_row.conrelid = 'public.users'::regclass
      and constraint_row.conname = 'users_registration_submission_boundary_check'
  ) then
    alter table public.users
      add constraint users_registration_submission_boundary_check check (
        (
          registration_submitted_at is null
          and created_at is not null
          and (
            created_at < timestamptz '2026-10-23 18:01:51.842574+00'
            or (
              is_guest is true
              and email is not null
              and pg_catalog.lower(pg_catalog.btrim(email)) =
                'guest-' || id::text || '@guest.askcrump.local'
            )
          )
        )
        or (
          registration_submitted_at is not null
          and registration_environment is not null
          and created_at is not null
          and registration_submitted_at >= created_at
        )
      );
  end if;
end
$migration$;

create index if not exists users_registration_submission_cohort_idx
  on public.users(
    (
      case
        when registration_submitted_at is not null
          then registration_submitted_at
        when is_guest is false
          then created_at
        else null
      end
    ),
    registration_environment,
    id
  )
  where deleted_at is null;

create or replace function public.enforce_registration_submission_immutability_v1()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  if tg_op = 'INSERT' then
    if new.registration_submitted_at is null and new.is_guest is false then
      if new.registration_environment is null or new.created_at is null then
        raise exception 'Registration boundary is required for a new account.'
          using errcode = '23514';
      end if;

      -- Keep old application instances safe during schema-first rollout and
      -- rollback: a fresh non-guest insert still receives a durable boundary.
      new.registration_submitted_at := greatest(
        pg_catalog.statement_timestamp(),
        new.created_at
      );
    end if;

    return new;
  end if;

  if old.registration_submitted_at is not null then
    new.registration_submitted_at := old.registration_submitted_at;
    new.registration_environment := old.registration_environment;
  elsif old.is_guest is true
        and old.email is not null
        and pg_catalog.lower(pg_catalog.btrim(old.email)) =
          'guest-' || old.id::text || '@guest.askcrump.local'
        and new.email is not null
        and pg_catalog.lower(pg_catalog.btrim(new.email)) <>
          'guest-' || old.id::text || '@guest.askcrump.local' then
    if new.registration_environment is null then
      raise exception 'Registration environment is required for guest conversion.'
        using errcode = '23514';
    end if;

    -- This database fallback closes the schema-before-code deployment window:
    -- an older application instance can still convert a preview identity while
    -- the new release rolls out, but it cannot create an unmarked cohort row.
    new.registration_submitted_at := greatest(
      coalesce(new.registration_submitted_at, pg_catalog.statement_timestamp()),
      new.created_at
    );
  elsif new.registration_submitted_at is not null
        and (
          new.registration_environment is null
          or new.created_at is null
          or new.registration_submitted_at < new.created_at
        ) then
    raise exception 'Registration submission boundary is invalid.'
      using errcode = '23514';
  end if;

  return new;
end;
$$;

drop trigger if exists users_registration_submission_insert_v1
  on public.users;
create trigger users_registration_submission_insert_v1
before insert
on public.users
for each row
execute function public.enforce_registration_submission_immutability_v1();

drop trigger if exists users_registration_submission_immutability_v1
  on public.users;
create trigger users_registration_submission_immutability_v1
before update of registration_submitted_at, registration_environment, email
on public.users
for each row
execute function public.enforce_registration_submission_immutability_v1();

revoke all on function public.enforce_registration_submission_immutability_v1()
  from public, anon, authenticated, service_role;

-- Rewrite only the three u.created_at cohort anchors in each reviewed report.
-- Fail closed if an earlier migration changed the expected function shape.
do $migration$
declare
  v_signature regprocedure;
  v_definition text;
  v_anchor_count integer;
  v_registration_anchor constant text := $anchor$(
        case
          when u.registration_submitted_at is not null
            then u.registration_submitted_at
          when u.is_guest is false
            then u.created_at
          else null
        end
      )$anchor$;
begin
  foreach v_signature in array array[
    'public.product_growth_funnel_snapshot(timestamptz,timestamptz,text,boolean)'::regprocedure,
    'public.product_weekly_attribution_export(timestamptz,timestamptz,text,boolean)'::regprocedure,
    'public.product_project_continuity_snapshot(timestamptz,timestamptz,text,boolean)'::regprocedure
  ]
  loop
    select pg_catalog.pg_get_functiondef(v_signature)
      into v_definition;

    v_anchor_count := (
      pg_catalog.length(v_definition)
      - pg_catalog.length(pg_catalog.replace(v_definition, 'u.created_at', ''))
    ) / pg_catalog.length('u.created_at');

    if v_anchor_count <> 3
       or pg_catalog.strpos(v_definition, 'registration_submitted_at') > 0 then
      raise exception 'Unexpected growth cohort definition for %; refusing rewrite.',
        v_signature::text
        using errcode = '55000';
    end if;

    execute pg_catalog.replace(
      v_definition,
      'u.created_at',
      v_registration_anchor
    );
  end loop;
end
$migration$;

comment on function public.product_growth_funnel_snapshot(
  timestamptz, timestamptz, text, boolean
) is
  'Service-role-only, content-free aggregate funnel anchored to first accepted registration submission, with created_at fallback only for non-guest legacy accounts. Stage 4 is optional profile-name completion, not required onboarding or activation; D1/D7 denominators remain activation-based.';

comment on function public.product_weekly_attribution_export(
  timestamptz, timestamptz, text, boolean
) is
  'Service-role-only, content-free weekly cohort anchored to durable registration submission and grouped by first-touch attribution when present. Non-guest legacy accounts retain created_at fallback; finance fields remain null.';

comment on function public.product_project_continuity_snapshot(
  timestamptz, timestamptz, text, boolean
) is
  'Service-role-only, content-free registration cohort comparing save offers, intent, completed saves, and Project resume. Preview-only guests are excluded and non-guest legacy accounts retain created_at fallback.';

revoke all on function public.product_growth_funnel_snapshot(
  timestamptz, timestamptz, text, boolean
) from public, anon, authenticated;
revoke all on function public.product_weekly_attribution_export(
  timestamptz, timestamptz, text, boolean
) from public, anon, authenticated;
revoke all on function public.product_project_continuity_snapshot(
  timestamptz, timestamptz, text, boolean
) from public, anon, authenticated;

grant execute on function public.product_growth_funnel_snapshot(
  timestamptz, timestamptz, text, boolean
) to service_role;
grant execute on function public.product_weekly_attribution_export(
  timestamptz, timestamptz, text, boolean
) to service_role;
grant execute on function public.product_project_continuity_snapshot(
  timestamptz, timestamptz, text, boolean
) to service_role;

commit;
