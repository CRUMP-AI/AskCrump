-- Ask Crump verified-user journey measurement correction.
-- Record the first inbox-control proof once at the database boundary, then keep
-- registered-user value and retention signals strictly after that boundary.

begin;

set local lock_timeout = '5s';
set local statement_timeout = '30s';

alter table public.users
  add column if not exists email_verified_at timestamptz;

comment on column public.users.email_verified_at is
  'First database-observed transition to verified email ownership. Null means unverified or legacy timing unavailable; immutable once populated.';

do $migration$
begin
  if not exists (
    select 1
    from pg_catalog.pg_constraint as constraint_row
    where constraint_row.conrelid = 'public.users'::regclass
      and constraint_row.conname = 'users_email_verified_at_boundary_check'
  ) then
    alter table public.users
      add constraint users_email_verified_at_boundary_check check (
        email_verified_at is null
        or (
          is_verified is true
          and created_at is not null
          and email_verified_at >= created_at
        )
      ) not valid;
  end if;
end
$migration$;

alter table public.users
  validate constraint users_email_verified_at_boundary_check;

create or replace function public.enforce_email_verification_timestamp_v1()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  if tg_op = 'INSERT' then
    if coalesce(new.is_verified, false) then
      -- Never trust an application-supplied verification timestamp. A row born
      -- verified receives the database statement time, while historical rows
      -- that predate this migration remain null because they are not rewritten.
      new.email_verified_at := pg_catalog.statement_timestamp();
    else
      new.email_verified_at := null;
    end if;

    return new;
  end if;

  if old.email_verified_at is not null then
    new.email_verified_at := old.email_verified_at;
  elsif old.is_verified is false and new.is_verified is true then
    -- This covers ordinary verification, password-reset inbox proof, and the
    -- atomic guest verification RPC without trusting an application clock.
    new.email_verified_at := pg_catalog.statement_timestamp();
  else
    -- Do not fabricate timing for already-verified legacy accounts and do not
    -- accept a caller-supplied timestamp on an unrelated update.
    new.email_verified_at := null;
  end if;

  return new;
end;
$$;

drop trigger if exists users_email_verification_timestamp_v1
  on public.users;
create trigger users_email_verification_timestamp_v1
before insert or update of is_verified, email_verified_at
on public.users
for each row
execute function public.enforce_email_verification_timestamp_v1();

revoke all on function public.enforce_email_verification_timestamp_v1()
  from public, anon, authenticated, service_role;

-- Rewrite the existing service-only aggregates in place. Keep AccountCreated
-- attribution anchored to registration, but admit every later lifecycle event
-- and durable fallback only after an immutable verification boundary. Legacy
-- verified rows with unknown timing remain unavailable instead of receiving a
-- fabricated timestamp.
do $migration$
declare
  v_signature regprocedure;
  v_definition text;
  v_function_name text;
  v_old_fragments text[];
  v_new_fragments text[];
  v_expected_counts integer[];
  v_count integer;
  v_index integer;
begin
  foreach v_signature in array array[
    'public.product_growth_funnel_snapshot(timestamptz,timestamptz,text,boolean)'::regprocedure,
    'public.product_weekly_attribution_export(timestamptz,timestamptz,text,boolean)'::regprocedure
  ]
  loop
    select
      function_row.proname,
      pg_catalog.pg_get_functiondef(function_row.oid)
      into strict v_function_name, v_definition
      from pg_catalog.pg_proc as function_row
      where function_row.oid = v_signature;

    if pg_catalog.strpos(v_definition, 'email_verified_at') > 0 then
      raise exception 'Unexpected preexisting verification timing in %; refusing rewrite.',
        v_signature::text
        using errcode = '55000';
    end if;

    v_old_fragments := array[
      $old$      u.is_verified,$old$,
      $old$      c.is_verified,$old$,
      $old$      and e.created_at >= c.cohort_at$old$,
      $old$                and j.status = 'completed'
                and j.updated_at >= f.cohort_at$old$,
      $old$f.cohort_at$old$
    ];
    v_new_fragments := array[
      $new$      u.is_verified,
      u.email_verified_at,$new$,
      $new$      c.is_verified,
      c.email_verified_at,$new$,
      $new$      and e.created_at >= c.cohort_at
      and (
        e.event_name = 'AccountCreated'
        or (
          c.email_verified_at is not null
          and c.email_verified_at < p_until
          and e.created_at >= c.email_verified_at
        )
      )$new$,
      $new$                and j.status = 'completed'
                and j.created_at >= f.email_verified_at
                and j.updated_at >= f.email_verified_at$new$,
      $new$f.email_verified_at$new$
    ];

    if v_function_name = 'product_growth_funnel_snapshot' then
      v_expected_counts := array[1, 2, 1, 1, 3];
      v_old_fragments := v_old_fragments || array[
        $old$count(*) filter (where is_verified)$old$
      ];
      v_new_fragments := v_new_fragments || array[
        $new$count(*) filter (
        where is_verified
          and email_verified_at is not null
          and email_verified_at < p_until
      )$new$
      ];
      v_expected_counts := v_expected_counts || array[1];
      v_old_fragments := v_old_fragments || array[
        $old$        where subscription_tier in ('professional', 'enterprise')
          and subscription_status in ('active', 'trialing')
      ) as active_paid_accounts$old$
      ];
      v_new_fragments := v_new_fragments || array[
        $new$        where subscription_tier in ('professional', 'enterprise')
          and subscription_status in ('active', 'trialing')
          and email_verified_at is not null
          and email_verified_at < p_until
      ) as active_paid_accounts$new$
      ];
      v_expected_counts := v_expected_counts || array[1];
    elsif v_function_name = 'product_weekly_attribution_export' then
      v_expected_counts := array[1, 2, 1, 1, 14];
      v_old_fragments := v_old_fragments || array[
        $old$count(*) filter (where j.is_verified)::bigint$old$
      ];
      v_new_fragments := v_new_fragments || array[
        $new$count(*) filter (
      where j.is_verified
        and j.email_verified_at is not null
        and j.email_verified_at < p_until
    )::bigint$new$
      ];
      v_expected_counts := v_expected_counts || array[1];
      v_old_fragments := v_old_fragments || array[
        $old$      (
        signals.subscription_tier in ('professional', 'enterprise')
        and signals.subscription_status = 'active'
        and signals.subscription_provider in ('stripe', 'revenuecat')
      ) as active_subscription_payer$old$
      ];
      v_new_fragments := v_new_fragments || array[
        $new$      (
        signals.subscription_tier in ('professional', 'enterprise')
        and signals.subscription_status = 'active'
        and signals.subscription_provider in ('stripe', 'revenuecat')
        and signals.email_verified_at is not null
        and signals.email_verified_at < p_until
      ) as active_subscription_payer$new$
      ];
      v_expected_counts := v_expected_counts || array[1];
    else
      raise exception 'Unexpected growth function %.', v_signature::text
        using errcode = '55000';
    end if;

    for v_index in 1..pg_catalog.array_length(v_old_fragments, 1)
    loop
      v_count := (
        pg_catalog.length(v_definition)
        - pg_catalog.length(
            pg_catalog.replace(v_definition, v_old_fragments[v_index], '')
          )
      ) / pg_catalog.length(v_old_fragments[v_index]);

      if v_count <> v_expected_counts[v_index] then
        raise exception
          'Unexpected % definition at rewrite %: expected %, found %.',
          v_signature::text,
          v_index,
          v_expected_counts[v_index],
          v_count
          using errcode = '55000';
      end if;

      v_definition := pg_catalog.replace(
        v_definition,
        v_old_fragments[v_index],
        v_new_fragments[v_index]
      );
    end loop;

    execute v_definition;
  end loop;
end
$migration$;

do $migration$
declare
  v_signature constant regprocedure :=
    'public.product_project_continuity_snapshot(timestamptz,timestamptz,text,boolean)'::regprocedure;
  v_definition text;
  v_old_fragments text[] := array[
    $old$      ) as cohort_at
    from public.users as u$old$,
    $old$      and e.created_at >= c.cohort_at$old$
  ];
  v_new_fragments text[] := array[
    $new$      ) as cohort_at,
      u.email_verified_at
    from public.users as u$new$,
    $new$      and c.email_verified_at is not null
      and c.email_verified_at < p_until
      and e.created_at >= c.email_verified_at$new$
  ];
  v_count integer;
  v_index integer;
begin
  select pg_catalog.pg_get_functiondef(v_signature)
    into strict v_definition;

  if pg_catalog.strpos(v_definition, 'email_verified_at') > 0 then
    raise exception 'Unexpected preexisting verification timing in %; refusing rewrite.',
      v_signature::text
      using errcode = '55000';
  end if;

  for v_index in 1..pg_catalog.array_length(v_old_fragments, 1)
  loop
    v_count := (
      pg_catalog.length(v_definition)
      - pg_catalog.length(
          pg_catalog.replace(v_definition, v_old_fragments[v_index], '')
        )
    ) / pg_catalog.length(v_old_fragments[v_index]);

    if v_count <> 1 then
      raise exception 'Unexpected % definition at rewrite %: expected 1, found %.',
        v_signature::text,
        v_index,
        v_count
        using errcode = '55000';
    end if;

    v_definition := pg_catalog.replace(
      v_definition,
      v_old_fragments[v_index],
      v_new_fragments[v_index]
    );
  end loop;

  execute v_definition;
end
$migration$;

comment on function public.product_growth_funnel_snapshot(
  timestamptz, timestamptz, text, boolean
) is
  'Service-role-only, content-free registration funnel. verified_now and every value/retention stage require a known immutable email verification time before p_until; legacy verification timing remains unavailable rather than fabricated.';

comment on function public.product_weekly_attribution_export(
  timestamptz, timestamptz, text, boolean
) is
  'Service-role-only, content-free registration cohort grouped by first-touch attribution. verified_now and all activation, durable-value, payer, and D1/D7 signals begin at known immutable email verification; legacy unknown timing is excluded and finance fields remain null.';

comment on function public.product_project_continuity_snapshot(
  timestamptz, timestamptz, text, boolean
) is
  'Service-role-only, content-free registration cohort. Project offer, intent, save, activation, and resume signals begin only after known immutable email verification; legacy unknown timing stays unavailable.';

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
