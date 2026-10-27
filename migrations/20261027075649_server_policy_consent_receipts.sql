-- Immutable policy manifests and append-only, server-timestamped acceptance
-- receipts. Application enforcement is deployed only after this additive
-- schema passes readback. The production migration runner owns the transaction.

set local lock_timeout = '5s';
set local statement_timeout = '30s';

do $preflight$
declare
  v_bundle_table regclass := pg_catalog.to_regclass('public.consent_policy_bundles');
  v_receipt_table regclass := pg_catalog.to_regclass('public.user_policy_acceptance_receipts');
  v_assert_function regprocedure := pg_catalog.to_regprocedure(
    'public.assert_policy_consent_schema_v1()'
  );
begin
  if pg_catalog.to_regclass('public.users') is null then
    raise exception 'Policy-receipt prerequisite public.users is missing.'
      using errcode = '55000';
  end if;

  if not exists (
    select 1 from pg_catalog.pg_roles where rolname = 'anon'
  ) or not exists (
    select 1 from pg_catalog.pg_roles where rolname = 'authenticated'
  ) or not exists (
    select 1 from pg_catalog.pg_roles where rolname = 'service_role'
  ) then
    raise exception 'Policy-receipt database roles are missing.'
      using errcode = '55000';
  end if;

  if (
    select count(*)
      from pg_catalog.pg_attribute as attribute_row
     where attribute_row.attrelid = 'public.users'::regclass
       and attribute_row.attnum > 0
       and not attribute_row.attisdropped
       and (
         (attribute_row.attname = 'id' and attribute_row.atttypid = 'pg_catalog.uuid'::regtype)
         or (attribute_row.attname = 'is_guest' and attribute_row.atttypid = 'pg_catalog.bool'::regtype)
         or (attribute_row.attname = 'is_verified' and attribute_row.atttypid = 'pg_catalog.bool'::regtype)
         or (attribute_row.attname = 'registration_submitted_at' and attribute_row.atttypid = 'pg_catalog.timestamptz'::regtype)
         or (attribute_row.attname = 'terms_accepted_at' and attribute_row.atttypid = 'pg_catalog.timestamptz'::regtype)
         or (attribute_row.attname = 'terms_version' and attribute_row.atttypid = 'pg_catalog.text'::regtype)
         or (attribute_row.attname = 'updated_at' and attribute_row.atttypid = 'pg_catalog.timestamptz'::regtype)
         or (attribute_row.attname = 'deleted_at' and attribute_row.atttypid = 'pg_catalog.timestamptz'::regtype)
       )
  ) <> 8 then
    raise exception 'Unexpected public.users policy-receipt prerequisites.'
      using errcode = '55000';
  end if;

  if (v_bundle_table is null) <> (v_receipt_table is null) then
    raise exception 'Partial policy-consent schema detected.' using errcode = '55000';
  end if;

  if v_bundle_table is not null then
    if v_assert_function is null or not (
      select not function_row.prosecdef
         and function_row.proconfig = array['search_path=""']::text[]
         and pg_catalog.pg_get_userbyid(function_row.proowner) = 'postgres'
         and pg_catalog.md5(function_row.prosrc) = '5f1ac35d767abaebf4968db2e9600967'
        from pg_catalog.pg_proc as function_row
       where function_row.oid = v_assert_function
    ) or exists (
      select 1
        from pg_catalog.pg_proc as function_row,
             lateral pg_catalog.aclexplode(
               coalesce(
                 function_row.proacl,
                 pg_catalog.acldefault('f', function_row.proowner)
               )
             ) as acl_row
       where function_row.oid = v_assert_function
         and acl_row.grantee <> function_row.proowner
    ) then
      raise exception 'Policy schema assertion guard is missing or drifted.'
        using errcode = '55000';
    end if;
    perform public.assert_policy_consent_schema_v1();
  elsif exists (
    select 1
      from pg_catalog.pg_proc as function_row
      join pg_catalog.pg_namespace as namespace_row
        on namespace_row.oid = function_row.pronamespace
     where namespace_row.nspname = 'public'
       and function_row.proname in (
         'record_policy_acceptance_v1',
         'read_current_policy_acceptance_v1',
         'reject_policy_acceptance_receipt_mutation_v1',
         'assert_policy_consent_schema_v1'
       )
  ) then
    raise exception 'Partial policy-consent function set detected.' using errcode = '55000';
  end if;
end;
$preflight$;

create table if not exists public.consent_policy_bundles (
  bundle_id text primary key,
  effective_date date not null,
  legal_path text not null,
  canonicalization text not null,
  legal_document_sha256 text not null,
  policy_sections_sha256 text not null,
  registration_disclosure_sha256 text not null,
  fallback_disclosure_sha256 text not null,
  terms_component_id text not null,
  terms_sha256 text not null,
  privacy_component_id text not null,
  privacy_sha256 text not null,
  age_attestation_component_id text not null,
  age_attestation_sha256 text not null,
  provider_disclosure_component_id text not null,
  provider_disclosure_sha256 text not null,
  created_at timestamptz not null default pg_catalog.clock_timestamp(),
  constraint consent_policy_bundles_bundle_id_check check (
    bundle_id ~ '^ask-crump-legal-[0-9]{4}-[0-9]{2}-[0-9]{2}-[0-9a-f]{8}$'
  ),
  constraint consent_policy_bundles_legal_path_check check (legal_path = '/legal.html'),
  constraint consent_policy_bundles_canonicalization_check check (
    canonicalization = 'html-section-outerhtml-lf-v1'
  ),
  constraint consent_policy_bundles_document_hash_check check (
    legal_document_sha256 ~ '^[0-9a-f]{64}$'
  ),
  constraint consent_policy_bundles_sections_hash_check check (
    policy_sections_sha256 ~ '^[0-9a-f]{64}$'
  ),
  constraint consent_policy_bundles_registration_hash_check check (
    registration_disclosure_sha256 ~ '^[0-9a-f]{64}$'
  ),
  constraint consent_policy_bundles_fallback_hash_check check (
    fallback_disclosure_sha256 ~ '^[0-9a-f]{64}$'
  ),
  constraint consent_policy_bundles_terms_component_check check (
    terms_component_id ~ '^ask-crump-[a-z0-9-]+-v[0-9]+$'
    and terms_sha256 ~ '^[0-9a-f]{64}$'
  ),
  constraint consent_policy_bundles_privacy_component_check check (
    privacy_component_id ~ '^ask-crump-[a-z0-9-]+-v[0-9]+$'
    and privacy_sha256 ~ '^[0-9a-f]{64}$'
  ),
  constraint consent_policy_bundles_age_component_check check (
    age_attestation_component_id ~ '^ask-crump-[a-z0-9-]+-v[0-9]+$'
    and age_attestation_sha256 ~ '^[0-9a-f]{64}$'
  ),
  constraint consent_policy_bundles_provider_component_check check (
    provider_disclosure_component_id ~ '^ask-crump-[a-z0-9-]+-v[0-9]+$'
    and provider_disclosure_sha256 ~ '^[0-9a-f]{64}$'
  )
);

alter table public.consent_policy_bundles owner to postgres;
alter table public.consent_policy_bundles enable row level security;

create table if not exists public.user_policy_acceptance_receipts (
  id uuid primary key default pg_catalog.gen_random_uuid(),
  user_id uuid not null,
  bundle_id text not null,
  acceptance_source text not null,
  client_platform text not null,
  age_17_plus_attested boolean not null,
  terms_accepted boolean not null,
  privacy_notice_acknowledged boolean not null,
  ai_provider_transmission_authorized boolean not null,
  accepted_at timestamptz not null default pg_catalog.clock_timestamp(),
  constraint user_policy_acceptance_receipts_user_fkey
    foreign key (user_id) references public.users(id) on delete cascade,
  constraint user_policy_acceptance_receipts_bundle_fkey
    foreign key (bundle_id) references public.consent_policy_bundles(bundle_id)
    on update restrict on delete restrict,
  constraint user_policy_acceptance_receipts_source_check check (
    acceptance_source in ('registration', 'guest_gate', 'account_gate')
  ),
  constraint user_policy_acceptance_receipts_platform_check check (
    client_platform in ('web', 'native', 'unknown')
  ),
  constraint user_policy_acceptance_receipts_source_unique unique (
    user_id, bundle_id, acceptance_source
  ),
  constraint user_policy_acceptance_receipts_attestations_check check (
    age_17_plus_attested is true
    and terms_accepted is true
    and privacy_notice_acknowledged is true
    and ai_provider_transmission_authorized is true
  )
);

alter table public.user_policy_acceptance_receipts owner to postgres;
alter table public.user_policy_acceptance_receipts enable row level security;

create index if not exists user_policy_acceptance_receipts_current_idx
  on public.user_policy_acceptance_receipts (
    user_id, bundle_id, accepted_at desc, id desc
  );

insert into public.consent_policy_bundles (
  bundle_id,
  effective_date,
  legal_path,
  canonicalization,
  legal_document_sha256,
  policy_sections_sha256,
  registration_disclosure_sha256,
  fallback_disclosure_sha256,
  terms_component_id,
  terms_sha256,
  privacy_component_id,
  privacy_sha256,
  age_attestation_component_id,
  age_attestation_sha256,
  provider_disclosure_component_id,
  provider_disclosure_sha256
) values (
  'ask-crump-legal-2026-08-01-a44e8c36',
  date '2026-08-01',
  '/legal.html',
  'html-section-outerhtml-lf-v1',
  '72067fedd1a1f189b088e909eadebb9c9b86816064dcbe31f178c7b4dec499b5',
  'a44e8c3637047ccfda406e35310312b4ea068bed73244a753fee5c4f2173a83a',
  'f9f8e731dae7b009371538f8be561b458b6fb6b3bab54e4a3f18190aaec5ad61',
  '92b512f3bd4c3d4f44a38e5561b853be3f42ea6288cf20881ae21c5aa2e7cf2c',
  'ask-crump-terms-v1',
  '5ef56db9335386895dd9bfb90589e15d766bf9b7c4401defe4ec38568d98f258',
  'ask-crump-privacy-v1',
  '4191cbfbeb311232797c2645d7d2e4616dea6ca3cd7161f70b2caba0e88a8ddf',
  'ask-crump-age-17-v1',
  'd3d8e283bf73ceb97867d09d50497635fc875af042d3d4f0ea5d1122bd235b99',
  'ask-crump-ai-provider-disclosure-v1',
  'b145250398b66900d5f00687158cba029b0b5407c90d3a73ab8ca9fc4e809d73'
) on conflict (bundle_id) do nothing;

create or replace function public.reject_policy_acceptance_receipt_mutation_v1()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $function$
begin
  if tg_op = 'DELETE'
     and pg_catalog.pg_trigger_depth() = 2
     and current_user = 'postgres'
     and tg_table_schema = 'public'
     and tg_table_name = 'user_policy_acceptance_receipts' then
    if not exists (
      select 1 from public.users as account where account.id = old.user_id
    ) then
      return old;
    end if;
  end if;
  raise exception 'Policy acceptance receipts are append-only.' using errcode = '55000';
end;
$function$;

alter function public.reject_policy_acceptance_receipt_mutation_v1() owner to postgres;

drop trigger if exists reject_consent_policy_bundle_update
  on public.consent_policy_bundles;
create trigger reject_consent_policy_bundle_update
before update on public.consent_policy_bundles
for each row execute function public.reject_policy_acceptance_receipt_mutation_v1();

drop trigger if exists reject_consent_policy_bundle_delete
  on public.consent_policy_bundles;
create trigger reject_consent_policy_bundle_delete
before delete on public.consent_policy_bundles
for each row execute function public.reject_policy_acceptance_receipt_mutation_v1();

drop trigger if exists reject_policy_acceptance_receipt_update
  on public.user_policy_acceptance_receipts;
create trigger reject_policy_acceptance_receipt_update
before update on public.user_policy_acceptance_receipts
for each row execute function public.reject_policy_acceptance_receipt_mutation_v1();

drop trigger if exists reject_policy_acceptance_receipt_delete
  on public.user_policy_acceptance_receipts;
create trigger reject_policy_acceptance_receipt_delete
before delete on public.user_policy_acceptance_receipts
for each row execute function public.reject_policy_acceptance_receipt_mutation_v1();

create or replace function public.record_policy_acceptance_v1(
  p_user_id uuid,
  p_bundle_id text,
  p_acceptance_source text,
  p_client_platform text,
  p_age_17_plus_attested boolean,
  p_terms_accepted boolean,
  p_privacy_notice_acknowledged boolean,
  p_ai_provider_transmission_authorized boolean
)
returns table (
  receipt_id uuid,
  accepted_at timestamptz,
  bundle_id text,
  bundle_hash text
)
language plpgsql
security definer
set search_path = ''
as $function$
declare
  v_user public.users%rowtype;
  v_receipt_id uuid := pg_catalog.gen_random_uuid();
  v_accepted_at timestamptz := pg_catalog.clock_timestamp();
begin
  if p_bundle_id is distinct from 'ask-crump-legal-2026-08-01-a44e8c36'
     or p_age_17_plus_attested is distinct from true
     or p_terms_accepted is distinct from true
     or p_privacy_notice_acknowledged is distinct from true
     or p_ai_provider_transmission_authorized is distinct from true
     or p_acceptance_source not in ('registration', 'guest_gate', 'account_gate')
     or p_client_platform not in ('web', 'native', 'unknown') then
    raise exception 'Invalid or stale policy acceptance.' using errcode = '22023';
  end if;

  if not exists (
    select 1
      from public.consent_policy_bundles as bundle
     where bundle.bundle_id = 'ask-crump-legal-2026-08-01-a44e8c36'
       and bundle.effective_date = date '2026-08-01'
       and bundle.legal_path = '/legal.html'
       and bundle.canonicalization = 'html-section-outerhtml-lf-v1'
       and bundle.legal_document_sha256 = '72067fedd1a1f189b088e909eadebb9c9b86816064dcbe31f178c7b4dec499b5'
       and bundle.policy_sections_sha256 = 'a44e8c3637047ccfda406e35310312b4ea068bed73244a753fee5c4f2173a83a'
       and bundle.registration_disclosure_sha256 = 'f9f8e731dae7b009371538f8be561b458b6fb6b3bab54e4a3f18190aaec5ad61'
       and bundle.fallback_disclosure_sha256 = '92b512f3bd4c3d4f44a38e5561b853be3f42ea6288cf20881ae21c5aa2e7cf2c'
       and bundle.terms_component_id = 'ask-crump-terms-v1'
       and bundle.terms_sha256 = '5ef56db9335386895dd9bfb90589e15d766bf9b7c4401defe4ec38568d98f258'
       and bundle.privacy_component_id = 'ask-crump-privacy-v1'
       and bundle.privacy_sha256 = '4191cbfbeb311232797c2645d7d2e4616dea6ca3cd7161f70b2caba0e88a8ddf'
       and bundle.age_attestation_component_id = 'ask-crump-age-17-v1'
       and bundle.age_attestation_sha256 = 'd3d8e283bf73ceb97867d09d50497635fc875af042d3d4f0ea5d1122bd235b99'
       and bundle.provider_disclosure_component_id = 'ask-crump-ai-provider-disclosure-v1'
       and bundle.provider_disclosure_sha256 = 'b145250398b66900d5f00687158cba029b0b5407c90d3a73ab8ca9fc4e809d73'
  ) then
    raise exception 'Current policy manifest is missing or drifted.' using errcode = '55000';
  end if;

  select account.*
    into v_user
    from public.users as account
   where account.id = p_user_id
     and account.deleted_at is null
   for update;
  if not found then
    raise exception 'Policy-acceptance account is unavailable.' using errcode = 'P0002';
  end if;

  if p_acceptance_source = 'registration'
     and v_user.registration_submitted_at is null then
    raise exception 'Registration provenance is unavailable.' using errcode = '22023';
  elsif p_acceptance_source = 'guest_gate'
        and v_user.is_guest is distinct from true then
    raise exception 'Guest acceptance source does not match account state.' using errcode = '22023';
  elsif p_acceptance_source = 'account_gate'
        and v_user.is_guest is true then
    raise exception 'Account acceptance source does not match account state.' using errcode = '22023';
  end if;

  insert into public.user_policy_acceptance_receipts (
    id,
    user_id,
    bundle_id,
    acceptance_source,
    client_platform,
    age_17_plus_attested,
    terms_accepted,
    privacy_notice_acknowledged,
    ai_provider_transmission_authorized,
    accepted_at
  ) values (
    v_receipt_id,
    p_user_id,
    p_bundle_id,
    p_acceptance_source,
    p_client_platform,
    true,
    true,
    true,
    true,
    v_accepted_at
  ) on conflict on constraint user_policy_acceptance_receipts_source_unique
    do nothing;

  select receipt.id, receipt.accepted_at
    into strict v_receipt_id, v_accepted_at
    from public.user_policy_acceptance_receipts as receipt
   where receipt.user_id = p_user_id
     and receipt.bundle_id = p_bundle_id
     and receipt.acceptance_source = p_acceptance_source;

  update public.users as account
     set terms_accepted_at = v_accepted_at,
         terms_version = p_bundle_id,
         updated_at = greatest(account.updated_at, v_accepted_at)
   where account.id = p_user_id;

  return query select
    v_receipt_id,
    v_accepted_at,
    p_bundle_id,
    'a44e8c3637047ccfda406e35310312b4ea068bed73244a753fee5c4f2173a83a'::text;
end;
$function$;

alter function public.record_policy_acceptance_v1(
  uuid, text, text, text, boolean, boolean, boolean, boolean
) owner to postgres;

create or replace function public.read_current_policy_acceptance_v1(
  p_user_id uuid
)
returns table (
  receipt_id uuid,
  accepted_at timestamptz,
  bundle_id text,
  bundle_hash text,
  acceptance_source text
)
language plpgsql
security definer
stable
set search_path = ''
as $function$
begin
  if not exists (
    select 1
      from public.consent_policy_bundles as bundle
     where bundle.bundle_id = 'ask-crump-legal-2026-08-01-a44e8c36'
       and bundle.policy_sections_sha256 = 'a44e8c3637047ccfda406e35310312b4ea068bed73244a753fee5c4f2173a83a'
       and bundle.terms_component_id = 'ask-crump-terms-v1'
       and bundle.terms_sha256 = '5ef56db9335386895dd9bfb90589e15d766bf9b7c4401defe4ec38568d98f258'
       and bundle.privacy_component_id = 'ask-crump-privacy-v1'
       and bundle.privacy_sha256 = '4191cbfbeb311232797c2645d7d2e4616dea6ca3cd7161f70b2caba0e88a8ddf'
       and bundle.age_attestation_component_id = 'ask-crump-age-17-v1'
       and bundle.age_attestation_sha256 = 'd3d8e283bf73ceb97867d09d50497635fc875af042d3d4f0ea5d1122bd235b99'
       and bundle.provider_disclosure_component_id = 'ask-crump-ai-provider-disclosure-v1'
       and bundle.provider_disclosure_sha256 = 'b145250398b66900d5f00687158cba029b0b5407c90d3a73ab8ca9fc4e809d73'
  ) then
    raise exception 'Current policy manifest is missing or drifted.' using errcode = '55000';
  end if;

  return query
  select
    receipt.id,
    receipt.accepted_at,
    receipt.bundle_id,
    'a44e8c3637047ccfda406e35310312b4ea068bed73244a753fee5c4f2173a83a'::text,
    receipt.acceptance_source
  from public.user_policy_acceptance_receipts as receipt
  join public.users as account on account.id = receipt.user_id
  where receipt.user_id = p_user_id
    and receipt.bundle_id = 'ask-crump-legal-2026-08-01-a44e8c36'
    and receipt.age_17_plus_attested is true
    and receipt.terms_accepted is true
    and receipt.privacy_notice_acknowledged is true
    and receipt.ai_provider_transmission_authorized is true
    and account.deleted_at is null
  order by receipt.accepted_at desc, receipt.id desc
  limit 1;
end;
$function$;

alter function public.read_current_policy_acceptance_v1(uuid) owner to postgres;

create or replace function public.assert_policy_consent_schema_v1()
returns void
language plpgsql
security invoker
set search_path = ''
as $assert_function$
declare
  v_bundle_table regclass := 'public.consent_policy_bundles'::regclass;
  v_receipt_table regclass := 'public.user_policy_acceptance_receipts'::regclass;
  v_service_role oid := (
    select role_row.oid from pg_catalog.pg_roles as role_row
     where role_row.rolname = 'service_role'
  );
  v_function regprocedure;
begin
  if (
    select pg_catalog.array_agg(
      pg_catalog.format(
        '%s:%s.%s:%s:%s',
        attribute_row.attname,
        type_namespace.nspname,
        type_row.typname,
        attribute_row.attnotnull,
        attribute_row.atthasdef
      ) order by attribute_row.attnum
    )
      from pg_catalog.pg_attribute as attribute_row
      join pg_catalog.pg_type as type_row on type_row.oid = attribute_row.atttypid
      join pg_catalog.pg_namespace as type_namespace on type_namespace.oid = type_row.typnamespace
     where attribute_row.attrelid = v_bundle_table
       and attribute_row.attnum > 0
       and not attribute_row.attisdropped
  ) is distinct from array[
    'bundle_id:pg_catalog.text:t:f',
    'effective_date:pg_catalog.date:t:f',
    'legal_path:pg_catalog.text:t:f',
    'canonicalization:pg_catalog.text:t:f',
    'legal_document_sha256:pg_catalog.text:t:f',
    'policy_sections_sha256:pg_catalog.text:t:f',
    'registration_disclosure_sha256:pg_catalog.text:t:f',
    'fallback_disclosure_sha256:pg_catalog.text:t:f',
    'terms_component_id:pg_catalog.text:t:f',
    'terms_sha256:pg_catalog.text:t:f',
    'privacy_component_id:pg_catalog.text:t:f',
    'privacy_sha256:pg_catalog.text:t:f',
    'age_attestation_component_id:pg_catalog.text:t:f',
    'age_attestation_sha256:pg_catalog.text:t:f',
    'provider_disclosure_component_id:pg_catalog.text:t:f',
    'provider_disclosure_sha256:pg_catalog.text:t:f',
    'created_at:pg_catalog.timestamptz:t:t'
  ]::text[] then
    raise exception 'Policy manifest column drift detected.' using errcode = '55000';
  end if;

  if (
    select pg_catalog.array_agg(
      pg_catalog.format(
        '%s:%s.%s:%s:%s',
        attribute_row.attname,
        type_namespace.nspname,
        type_row.typname,
        attribute_row.attnotnull,
        attribute_row.atthasdef
      ) order by attribute_row.attnum
    )
      from pg_catalog.pg_attribute as attribute_row
      join pg_catalog.pg_type as type_row on type_row.oid = attribute_row.atttypid
      join pg_catalog.pg_namespace as type_namespace on type_namespace.oid = type_row.typnamespace
     where attribute_row.attrelid = v_receipt_table
       and attribute_row.attnum > 0
       and not attribute_row.attisdropped
  ) is distinct from array[
    'id:pg_catalog.uuid:t:t',
    'user_id:pg_catalog.uuid:t:f',
    'bundle_id:pg_catalog.text:t:f',
    'acceptance_source:pg_catalog.text:t:f',
    'client_platform:pg_catalog.text:t:f',
    'age_17_plus_attested:pg_catalog.bool:t:f',
    'terms_accepted:pg_catalog.bool:t:f',
    'privacy_notice_acknowledged:pg_catalog.bool:t:f',
    'ai_provider_transmission_authorized:pg_catalog.bool:t:f',
    'accepted_at:pg_catalog.timestamptz:t:t'
  ]::text[] then
    raise exception 'Policy receipt column drift detected.' using errcode = '55000';
  end if;

  if not exists (
    select 1
      from pg_catalog.pg_attrdef as default_row
     where default_row.adrelid = v_bundle_table
       and default_row.adnum = 17
       and pg_catalog.replace(
             pg_catalog.replace(
               pg_catalog.pg_get_expr(default_row.adbin, default_row.adrelid),
               '"',
               ''
             ),
             'pg_catalog.',
             ''
           ) = 'clock_timestamp()'
  ) or not exists (
    select 1
      from pg_catalog.pg_attrdef as default_row
     where default_row.adrelid = v_receipt_table
       and default_row.adnum = 1
       and pg_catalog.replace(
             pg_catalog.replace(
               pg_catalog.pg_get_expr(default_row.adbin, default_row.adrelid),
               '"',
               ''
             ),
             'pg_catalog.',
             ''
           ) = 'gen_random_uuid()'
  ) or not exists (
    select 1
      from pg_catalog.pg_attrdef as default_row
     where default_row.adrelid = v_receipt_table
       and default_row.adnum = 10
       and pg_catalog.replace(
             pg_catalog.replace(
               pg_catalog.pg_get_expr(default_row.adbin, default_row.adrelid),
               '"',
               ''
             ),
             'pg_catalog.',
             ''
           ) = 'clock_timestamp()'
  ) then
    raise exception 'Policy default-expression drift detected.' using errcode = '55000';
  end if;

  if (
    select pg_catalog.array_agg(
      constraint_row.conname::text order by constraint_row.conname
    )
      from pg_catalog.pg_constraint as constraint_row
     where constraint_row.conrelid = v_bundle_table
  ) is distinct from array[
    'consent_policy_bundles_age_component_check',
    'consent_policy_bundles_bundle_id_check',
    'consent_policy_bundles_canonicalization_check',
    'consent_policy_bundles_document_hash_check',
    'consent_policy_bundles_fallback_hash_check',
    'consent_policy_bundles_legal_path_check',
    'consent_policy_bundles_pkey',
    'consent_policy_bundles_privacy_component_check',
    'consent_policy_bundles_provider_component_check',
    'consent_policy_bundles_registration_hash_check',
    'consent_policy_bundles_sections_hash_check',
    'consent_policy_bundles_terms_component_check'
  ]::text[] or (
    select pg_catalog.array_agg(
      constraint_row.conname::text order by constraint_row.conname
    )
      from pg_catalog.pg_constraint as constraint_row
     where constraint_row.conrelid = v_receipt_table
  ) is distinct from array[
    'user_policy_acceptance_receipts_attestations_check',
    'user_policy_acceptance_receipts_bundle_fkey',
    'user_policy_acceptance_receipts_pkey',
    'user_policy_acceptance_receipts_platform_check',
    'user_policy_acceptance_receipts_source_check',
    'user_policy_acceptance_receipts_source_unique',
    'user_policy_acceptance_receipts_user_fkey'
  ]::text[] or exists (
    select 1
      from pg_catalog.pg_constraint as constraint_row
     where constraint_row.conrelid in (v_bundle_table, v_receipt_table)
       and (
         not constraint_row.convalidated
         or constraint_row.condeferrable
         or constraint_row.condeferred
       )
  ) then
    raise exception 'Policy constraint-set drift detected.' using errcode = '55000';
  end if;

  if (
    select pg_catalog.jsonb_object_agg(
      constraint_row.conname,
      pg_catalog.md5(
        pg_catalog.regexp_replace(
          pg_catalog.replace(
            pg_catalog.replace(
              pg_catalog.pg_get_constraintdef(constraint_row.oid, true),
              '"',
              ''
            ),
            'pg_catalog.',
            ''
          ),
          '\s+',
          '',
          'g'
        )
      )
    )
      from pg_catalog.pg_constraint as constraint_row
     where constraint_row.conrelid in (v_bundle_table, v_receipt_table)
       and constraint_row.contype = 'c'
  ) is distinct from pg_catalog.jsonb_build_object(
    'consent_policy_bundles_age_component_check', '2c7de28494260468a8fcde08c6f90c36',
    'consent_policy_bundles_bundle_id_check', '803f659dc88f82d2347d5ee47e8c200d',
    'consent_policy_bundles_canonicalization_check', '9b496681bf8d9741677626449d435482',
    'consent_policy_bundles_document_hash_check', 'd0ce86df1434efafe2c530ea36a0ba30',
    'consent_policy_bundles_fallback_hash_check', 'd41598b7bed84ca99c213f62fcf55c89',
    'consent_policy_bundles_legal_path_check', '6f3b979bc8290b3c612abe278c564b41',
    'consent_policy_bundles_privacy_component_check', '1ec776ab8e9913d7735be16437ccbec5',
    'consent_policy_bundles_provider_component_check', '182dd402014556d34aa10f19c4fcac6e',
    'consent_policy_bundles_registration_hash_check', '814311f3fd09f9491f27cabc707b2d70',
    'consent_policy_bundles_sections_hash_check', 'da2bb075a21e3bc57401577d50261766',
    'consent_policy_bundles_terms_component_check', '802d98c24a204697aee2352db00e126c',
    'user_policy_acceptance_receipts_attestations_check', '61666b8979192990c0bdebe352c5bcdf',
    'user_policy_acceptance_receipts_platform_check', '325c9a36ecc9befd6f53095c301e8f2c',
    'user_policy_acceptance_receipts_source_check', 'a766ea39e7f1812752bc0c8a95d88888'
  ) then
    raise exception 'Policy CHECK-expression drift detected.' using errcode = '55000';
  end if;

  if not exists (
    select 1 from pg_catalog.pg_constraint as constraint_row
     where constraint_row.conrelid = v_bundle_table
       and constraint_row.conname = 'consent_policy_bundles_pkey'
       and constraint_row.contype = 'p'
       and constraint_row.conkey = array[1]::smallint[]
  ) or not exists (
    select 1 from pg_catalog.pg_constraint as constraint_row
     where constraint_row.conrelid = v_receipt_table
       and constraint_row.conname = 'user_policy_acceptance_receipts_pkey'
       and constraint_row.contype = 'p'
       and constraint_row.conkey = array[1]::smallint[]
  ) or not exists (
    select 1 from pg_catalog.pg_constraint as constraint_row
     where constraint_row.conrelid = v_receipt_table
       and constraint_row.conname = 'user_policy_acceptance_receipts_source_unique'
       and constraint_row.contype = 'u'
       and constraint_row.conkey = array[2, 3, 4]::smallint[]
  ) or not exists (
    select 1 from pg_catalog.pg_constraint as constraint_row
     where constraint_row.conrelid = v_receipt_table
       and constraint_row.conname = 'user_policy_acceptance_receipts_user_fkey'
       and constraint_row.contype = 'f'
       and constraint_row.conkey = array[2]::smallint[]
       and constraint_row.confrelid = 'public.users'::regclass
       and constraint_row.confdeltype = 'c'
       and constraint_row.confupdtype = 'a'
  ) or not exists (
    select 1 from pg_catalog.pg_constraint as constraint_row
     where constraint_row.conrelid = v_receipt_table
       and constraint_row.conname = 'user_policy_acceptance_receipts_bundle_fkey'
       and constraint_row.contype = 'f'
       and constraint_row.conkey = array[3]::smallint[]
       and constraint_row.confrelid = v_bundle_table
       and constraint_row.confkey = array[1]::smallint[]
       and constraint_row.confdeltype = 'r'
       and constraint_row.confupdtype = 'r'
  ) then
    raise exception 'Policy key-constraint drift detected.' using errcode = '55000';
  end if;

  if not exists (
    select 1
      from pg_catalog.pg_index as index_row
      join pg_catalog.pg_class as index_class on index_class.oid = index_row.indexrelid
     where index_row.indrelid = v_receipt_table
       and index_class.relname = 'user_policy_acceptance_receipts_current_idx'
       and index_row.indisvalid
       and index_row.indisready
       and not index_row.indisunique
       and index_row.indnkeyatts = 4
       and index_row.indkey::text = '2 3 10 1'
       and index_row.indoption::text = '0 0 3 3'
       and index_row.indexprs is null
       and index_row.indpred is null
       and index_class.relam = (
         select access_method.oid from pg_catalog.pg_am as access_method
          where access_method.amname = 'btree'
       )
  ) then
    raise exception 'Policy receipt lookup-index drift detected.' using errcode = '55000';
  end if;

  if (
    select count(*)
      from pg_catalog.pg_trigger as trigger_row
     where trigger_row.tgrelid in (v_bundle_table, v_receipt_table)
       and not trigger_row.tgisinternal
  ) <> 4 or not exists (
    select 1 from pg_catalog.pg_trigger as trigger_row
     where trigger_row.tgrelid = v_bundle_table
       and trigger_row.tgname = 'reject_consent_policy_bundle_update'
       and trigger_row.tgtype = 19
       and trigger_row.tgenabled = 'O'
       and trigger_row.tgfoid = 'public.reject_policy_acceptance_receipt_mutation_v1()'::regprocedure
  ) or not exists (
    select 1 from pg_catalog.pg_trigger as trigger_row
     where trigger_row.tgrelid = v_bundle_table
       and trigger_row.tgname = 'reject_consent_policy_bundle_delete'
       and trigger_row.tgtype = 11
       and trigger_row.tgenabled = 'O'
       and trigger_row.tgfoid = 'public.reject_policy_acceptance_receipt_mutation_v1()'::regprocedure
  ) or not exists (
    select 1 from pg_catalog.pg_trigger as trigger_row
     where trigger_row.tgrelid = v_receipt_table
       and trigger_row.tgname = 'reject_policy_acceptance_receipt_update'
       and trigger_row.tgtype = 19
       and trigger_row.tgenabled = 'O'
       and trigger_row.tgfoid = 'public.reject_policy_acceptance_receipt_mutation_v1()'::regprocedure
  ) or not exists (
    select 1 from pg_catalog.pg_trigger as trigger_row
     where trigger_row.tgrelid = v_receipt_table
       and trigger_row.tgname = 'reject_policy_acceptance_receipt_delete'
       and trigger_row.tgtype = 11
       and trigger_row.tgenabled = 'O'
       and trigger_row.tgfoid = 'public.reject_policy_acceptance_receipt_mutation_v1()'::regprocedure
  ) then
    raise exception 'Policy immutability-trigger drift detected.' using errcode = '55000';
  end if;

  foreach v_function in array array[
    'public.record_policy_acceptance_v1(uuid,text,text,text,boolean,boolean,boolean,boolean)'::regprocedure,
    'public.read_current_policy_acceptance_v1(uuid)'::regprocedure
  ] loop
    if not (
      select function_row.prosecdef
         and function_row.proconfig = array['search_path=""']::text[]
         and pg_catalog.pg_get_userbyid(function_row.proowner) = 'postgres'
        from pg_catalog.pg_proc as function_row
       where function_row.oid = v_function
    ) or exists (
      select 1
        from pg_catalog.pg_proc as function_row,
             lateral pg_catalog.aclexplode(
               coalesce(
                 function_row.proacl,
                 pg_catalog.acldefault('f', function_row.proowner)
               )
             ) as acl_row
       where function_row.oid = v_function
         and (
           acl_row.privilege_type <> 'EXECUTE'
           or acl_row.grantee not in (function_row.proowner, v_service_role)
           or (acl_row.grantee = v_service_role and acl_row.is_grantable)
         )
    ) or not pg_catalog.has_function_privilege(
      'service_role', v_function, 'EXECUTE'
    ) then
      raise exception 'Policy RPC owner, search path, or ACL drift detected.'
        using errcode = '55000';
    end if;
  end loop;

  if (
    select pg_catalog.md5(function_row.prosrc)
      from pg_catalog.pg_proc as function_row
     where function_row.oid = 'public.record_policy_acceptance_v1(uuid,text,text,text,boolean,boolean,boolean,boolean)'::regprocedure
  ) <> '31c8f972cc8399d4f4629b06e255b888' or (
    select pg_catalog.md5(function_row.prosrc)
      from pg_catalog.pg_proc as function_row
     where function_row.oid = 'public.read_current_policy_acceptance_v1(uuid)'::regprocedure
  ) <> 'db366c127ad7dc9234e5e810f4d9062c' or (
    select pg_catalog.md5(function_row.prosrc)
      from pg_catalog.pg_proc as function_row
     where function_row.oid = 'public.reject_policy_acceptance_receipt_mutation_v1()'::regprocedure
  ) <> '9aa376abf59f1cdeea2dedca89d8535f' then
    raise exception 'Policy function-body drift detected.' using errcode = '55000';
  end if;

  foreach v_function in array array[
    'public.reject_policy_acceptance_receipt_mutation_v1()'::regprocedure,
    'public.assert_policy_consent_schema_v1()'::regprocedure
  ] loop
    if not (
      select not function_row.prosecdef
         and function_row.proconfig = array['search_path=""']::text[]
         and pg_catalog.pg_get_userbyid(function_row.proowner) = 'postgres'
        from pg_catalog.pg_proc as function_row
       where function_row.oid = v_function
    ) or exists (
      select 1
        from pg_catalog.pg_proc as function_row,
             lateral pg_catalog.aclexplode(
               coalesce(
                 function_row.proacl,
                 pg_catalog.acldefault('f', function_row.proowner)
               )
             ) as acl_row
       where function_row.oid = v_function
         and acl_row.grantee <> function_row.proowner
    ) then
      raise exception 'Policy guard function owner, search path, or ACL drift detected.'
        using errcode = '55000';
    end if;
  end loop;

  if (
    select count(*)
      from pg_catalog.pg_proc as function_row
      join pg_catalog.pg_namespace as namespace_row
        on namespace_row.oid = function_row.pronamespace
     where namespace_row.nspname = 'public'
       and function_row.proname in (
         'record_policy_acceptance_v1',
         'read_current_policy_acceptance_v1',
         'reject_policy_acceptance_receipt_mutation_v1',
         'assert_policy_consent_schema_v1'
       )
  ) <> 4 then
    raise exception 'Unexpected policy function overload detected.' using errcode = '55000';
  end if;

  foreach v_bundle_table in array array[
    'public.consent_policy_bundles'::regclass,
    'public.user_policy_acceptance_receipts'::regclass
  ] loop
    if not (
      select class_row.relkind = 'r'
         and class_row.relrowsecurity
         and not class_row.relforcerowsecurity
         and pg_catalog.pg_get_userbyid(class_row.relowner) = 'postgres'
        from pg_catalog.pg_class as class_row
       where class_row.oid = v_bundle_table
    ) or exists (
      select 1 from pg_catalog.pg_policy as policy_row
       where policy_row.polrelid = v_bundle_table
    ) or exists (
      select 1
        from pg_catalog.pg_class as class_row,
             lateral pg_catalog.aclexplode(
               coalesce(
                 class_row.relacl,
                 pg_catalog.acldefault('r', class_row.relowner)
               )
             ) as acl_row
       where class_row.oid = v_bundle_table
         and acl_row.grantee <> class_row.relowner
    ) or exists (
      select 1
        from pg_catalog.pg_attribute as attribute_row,
             lateral pg_catalog.aclexplode(attribute_row.attacl) as acl_row
       where attribute_row.attrelid = v_bundle_table
         and attribute_row.attnum > 0
         and not attribute_row.attisdropped
         and attribute_row.attacl is not null
         and acl_row.grantee <> (
           select class_row.relowner from pg_catalog.pg_class as class_row
            where class_row.oid = v_bundle_table
         )
    ) then
      raise exception 'Policy table owner, RLS, policy, or ACL drift detected.'
        using errcode = '55000';
    end if;
  end loop;

  if not exists (
    select 1
      from public.consent_policy_bundles as bundle
     where bundle.bundle_id = 'ask-crump-legal-2026-08-01-a44e8c36'
       and bundle.effective_date = date '2026-08-01'
       and bundle.legal_path = '/legal.html'
       and bundle.canonicalization = 'html-section-outerhtml-lf-v1'
       and bundle.legal_document_sha256 = '72067fedd1a1f189b088e909eadebb9c9b86816064dcbe31f178c7b4dec499b5'
       and bundle.policy_sections_sha256 = 'a44e8c3637047ccfda406e35310312b4ea068bed73244a753fee5c4f2173a83a'
       and bundle.registration_disclosure_sha256 = 'f9f8e731dae7b009371538f8be561b458b6fb6b3bab54e4a3f18190aaec5ad61'
       and bundle.fallback_disclosure_sha256 = '92b512f3bd4c3d4f44a38e5561b853be3f42ea6288cf20881ae21c5aa2e7cf2c'
       and bundle.terms_component_id = 'ask-crump-terms-v1'
       and bundle.terms_sha256 = '5ef56db9335386895dd9bfb90589e15d766bf9b7c4401defe4ec38568d98f258'
       and bundle.privacy_component_id = 'ask-crump-privacy-v1'
       and bundle.privacy_sha256 = '4191cbfbeb311232797c2645d7d2e4616dea6ca3cd7161f70b2caba0e88a8ddf'
       and bundle.age_attestation_component_id = 'ask-crump-age-17-v1'
       and bundle.age_attestation_sha256 = 'd3d8e283bf73ceb97867d09d50497635fc875af042d3d4f0ea5d1122bd235b99'
       and bundle.provider_disclosure_component_id = 'ask-crump-ai-provider-disclosure-v1'
       and bundle.provider_disclosure_sha256 = 'b145250398b66900d5f00687158cba029b0b5407c90d3a73ab8ca9fc4e809d73'
  ) then
    raise exception 'Current policy manifest is missing or drifted.' using errcode = '55000';
  end if;
end;
$assert_function$;

alter function public.assert_policy_consent_schema_v1() owner to postgres;

revoke all on table public.consent_policy_bundles
  from public, anon, authenticated, service_role;
revoke all on table public.user_policy_acceptance_receipts
  from public, anon, authenticated, service_role;
revoke all on function public.reject_policy_acceptance_receipt_mutation_v1()
  from public, anon, authenticated, service_role;
revoke all on function public.record_policy_acceptance_v1(
  uuid, text, text, text, boolean, boolean, boolean, boolean
) from public, anon, authenticated, service_role;
grant execute on function public.record_policy_acceptance_v1(
  uuid, text, text, text, boolean, boolean, boolean, boolean
) to service_role;
revoke all on function public.read_current_policy_acceptance_v1(uuid)
  from public, anon, authenticated, service_role;
grant execute on function public.read_current_policy_acceptance_v1(uuid)
  to service_role;
revoke all on function public.assert_policy_consent_schema_v1()
  from public, anon, authenticated, service_role;

comment on table public.consent_policy_bundles is
  'Immutable content-addressed legal-policy manifests; rows contain no customer data.';
comment on table public.user_policy_acceptance_receipts is
  'Append-only, server-timestamped acceptance provenance. Receipts cascade with account deletion.';
comment on function public.record_policy_acceptance_v1(
  uuid, text, text, text, boolean, boolean, boolean, boolean
) is 'Appends exact current policy acceptance and mirrors the database timestamp for rollback compatibility.';
comment on function public.read_current_policy_acceptance_v1(uuid) is
  'Returns only an exact current-bundle receipt for central server authorization.';
comment on function public.assert_policy_consent_schema_v1() is
  'Fails closed on policy manifest, receipt, constraint, trigger, function, RLS, or ACL drift.';

do $postflight$
begin
  if (
    select pg_catalog.md5(function_row.prosrc)
      from pg_catalog.pg_proc as function_row
     where function_row.oid = 'public.assert_policy_consent_schema_v1()'::regprocedure
  ) <> '5f1ac35d767abaebf4968db2e9600967' then
    raise exception 'Policy schema assertion guard body drifted during apply.'
      using errcode = '55000';
  end if;
  perform public.assert_policy_consent_schema_v1();
end;
$postflight$;
