-- Ask Crump 5.9.76
-- Content-free, service-role-only Vercel AI Gateway cost receipts.
-- No customer identifier, prompt, response, filename, URL, credential, or request body is stored.

begin;

set local lock_timeout = '5s';

create table if not exists public.ai_gateway_cost_receipts (
  id uuid primary key,
  environment text not null
    check (environment in ('production', 'preview', 'development', 'test')),
  deployment_id text not null,
  commit_sha text not null,
  purpose text not null
    check (purpose in ('chat', 'creation-intent', 'answer-verifier', 'check-in', 'planner', 'other')),
  expected_model text not null check (expected_model = 'openai/gpt-oss-20b'),
  expected_provider text not null check (expected_provider = 'groq'),
  authentication_lane text not null
    check (authentication_lane in ('oidc-project', 'api-key-attributed')),
  tags text[] not null,
  status text not null default 'attempted'
    check (status in ('attempted', 'completed', 'failed', 'rate_limited', 'budget_rejected')),
  error_code text,
  model text,
  provider text,
  input_tokens bigint not null default 0 check (input_tokens >= 0),
  output_tokens bigint not null default 0 check (output_tokens >= 0),
  cached_input_tokens bigint not null default 0 check (
    cached_input_tokens >= 0 and cached_input_tokens <= input_tokens
  ),
  gross_cost_usd numeric(18, 12),
  latency_ms integer not null default 0 check (latency_ms between 0 and 600000),
  usage_receipt_complete boolean not null default false,
  cost_receipt_complete boolean not null default false,
  created_at timestamptz not null default now(),
  settled_at timestamptz,
  constraint ai_gateway_cost_receipts_release_identity_check check (
    environment <> 'production'
    or (
      deployment_id ~ '^dpl_[A-Za-z0-9]{8,}$'
      and commit_sha ~ '^[0-9a-f]{40}$'
    )
  ),
  constraint ai_gateway_cost_receipts_deployment_id_check check (
    deployment_id = 'local' or deployment_id ~ '^dpl_[A-Za-z0-9]{8,}$'
  ),
  constraint ai_gateway_cost_receipts_commit_sha_check check (
    commit_sha ~ '^[0-9a-f]{40}$'
  ),
  constraint ai_gateway_cost_receipts_tags_check check (
    tags = array['tier:free', 'feature:' || purpose]::text[]
  ),
  constraint ai_gateway_cost_receipts_error_code_check check (
    error_code is null or error_code ~ '^[A-Z0-9_]{1,80}$'
  ),
  constraint ai_gateway_cost_receipts_model_check check (
    model is null or model ~ '^[a-z0-9][a-z0-9._/-]{0,119}$'
  ),
  constraint ai_gateway_cost_receipts_provider_check check (
    provider is null or provider ~ '^[a-z0-9][a-z0-9._-]{0,79}$'
  ),
  constraint ai_gateway_cost_receipts_cost_check check (
    gross_cost_usd is null or gross_cost_usd >= 0
  ),
  constraint ai_gateway_cost_receipts_settlement_check check (
    (
      status = 'attempted'
      and settled_at is null
      and error_code is null
      and model is null
      and provider is null
      and usage_receipt_complete is false
      and cost_receipt_complete is false
      and gross_cost_usd is null
    )
    or (
      status <> 'attempted'
      and settled_at is not null
      and model is not null
      and provider is not null
      and (status <> 'completed' or error_code is null)
      and (status = 'completed' or error_code is not null)
      and (cost_receipt_complete is false or gross_cost_usd is not null)
    )
  )
);

create index if not exists ai_gateway_cost_receipts_window_idx
  on public.ai_gateway_cost_receipts(environment, deployment_id, commit_sha, created_at);

create index if not exists ai_gateway_cost_receipts_incomplete_idx
  on public.ai_gateway_cost_receipts(created_at)
  where status = 'attempted'
    or usage_receipt_complete is false
    or cost_receipt_complete is false;

alter table public.ai_gateway_cost_receipts enable row level security;

revoke all on table public.ai_gateway_cost_receipts from public, anon, authenticated, service_role;

create or replace function public.claim_ai_gateway_cost_receipt(
  p_receipt_id uuid,
  p_environment text,
  p_deployment_id text,
  p_commit_sha text,
  p_purpose text,
  p_expected_model text,
  p_expected_provider text,
  p_authentication_lane text
)
returns boolean
language plpgsql
security definer
set search_path = ''
as $function$
begin
  if p_environment not in ('production', 'preview', 'development', 'test')
    or p_purpose not in ('chat', 'creation-intent', 'answer-verifier', 'check-in', 'planner', 'other')
    or p_expected_model <> 'openai/gpt-oss-20b'
    or p_expected_provider <> 'groq'
    or p_authentication_lane not in ('oidc-project', 'api-key-attributed')
  then
    return false;
  end if;

  insert into public.ai_gateway_cost_receipts (
    id,
    environment,
    deployment_id,
    commit_sha,
    purpose,
    expected_model,
    expected_provider,
    authentication_lane,
    tags
  ) values (
    p_receipt_id,
    p_environment,
    p_deployment_id,
    lower(p_commit_sha),
    p_purpose,
    p_expected_model,
    p_expected_provider,
    p_authentication_lane,
    array['tier:free', 'feature:' || p_purpose]::text[]
  )
  on conflict (id) do nothing;

  return found;
end;
$function$;

create or replace function public.settle_ai_gateway_cost_receipt(
  p_receipt_id uuid,
  p_status text,
  p_error_code text,
  p_model text,
  p_provider text,
  p_input_tokens bigint,
  p_output_tokens bigint,
  p_cached_input_tokens bigint,
  p_gross_cost_usd numeric,
  p_latency_ms integer,
  p_usage_receipt_complete boolean,
  p_cost_receipt_complete boolean
)
returns boolean
language plpgsql
security definer
set search_path = ''
as $function$
begin
  if p_status not in ('completed', 'failed', 'rate_limited', 'budget_rejected')
    or coalesce(p_model, '') !~ '^[a-z0-9][a-z0-9._/-]{0,119}$'
    or coalesce(p_provider, '') !~ '^[a-z0-9][a-z0-9._-]{0,79}$'
    or (p_error_code is not null and p_error_code !~ '^[A-Z0-9_]{1,80}$')
    or p_input_tokens < 0
    or p_output_tokens < 0
    or p_cached_input_tokens < 0
    or p_cached_input_tokens > p_input_tokens
    or p_latency_ms not between 0 and 600000
    or (p_gross_cost_usd is not null and p_gross_cost_usd < 0)
    or (p_cost_receipt_complete and p_gross_cost_usd is null)
    or (p_status = 'completed' and p_error_code is not null)
    or (p_status <> 'completed' and p_error_code is null)
  then
    return false;
  end if;

  update public.ai_gateway_cost_receipts
  set
    status = p_status,
    error_code = p_error_code,
    model = p_model,
    provider = p_provider,
    input_tokens = p_input_tokens,
    output_tokens = p_output_tokens,
    cached_input_tokens = p_cached_input_tokens,
    gross_cost_usd = p_gross_cost_usd,
    latency_ms = p_latency_ms,
    usage_receipt_complete = p_usage_receipt_complete,
    cost_receipt_complete = p_cost_receipt_complete,
    settled_at = now()
  where id = p_receipt_id
    and status = 'attempted';

  return found;
end;
$function$;

create or replace function public.ai_gateway_provider_cost_aggregate(
  p_since timestamptz,
  p_until timestamptz,
  p_environment text,
  p_deployment_id text,
  p_commit_sha text
)
returns table (
  window_since timestamptz,
  window_until timestamptz,
  environment text,
  deployment_id text,
  commit_sha text,
  model text,
  provider text,
  authentication_lane text,
  routing_tags text[],
  observed_purposes text[],
  all_gateway_calls_captured boolean,
  attempted bigint,
  completed bigint,
  failed bigint,
  rate_limited bigint,
  budget_rejected bigint,
  usage_receipts_complete boolean,
  cost_receipts_complete boolean,
  input_tokens bigint,
  output_tokens bigint,
  cached_input_tokens bigint,
  gross_provider_cost_usd numeric,
  cost_per_completed_request_usd numeric,
  unallocated_provider_cost_usd numeric,
  latency_p50_ms numeric,
  latency_p95_ms numeric,
  latency_max_ms integer,
  natural_production_completions bigint,
  synthetic_database_rows boolean,
  customer_content_returned boolean
)
language sql
stable
security definer
set search_path = ''
as $function$
  with scoped as (
    select *
    from public.ai_gateway_cost_receipts r
    where r.created_at >= p_since
      and r.created_at < p_until
      and r.environment = p_environment
      and r.deployment_id = p_deployment_id
      and r.commit_sha = lower(p_commit_sha)
  ), rollup as (
    select
      count(*)::bigint as attempted,
      count(*) filter (where status = 'completed')::bigint as completed,
      count(*) filter (where status <> 'completed')::bigint as failed,
      count(*) filter (where status = 'rate_limited')::bigint as rate_limited,
      count(*) filter (where status = 'budget_rejected')::bigint as budget_rejected,
      bool_and(status <> 'attempted' and usage_receipt_complete) as usage_complete,
      bool_and(status <> 'attempted' and cost_receipt_complete) as cost_complete,
      sum(input_tokens)::bigint as input_tokens,
      sum(output_tokens)::bigint as output_tokens,
      sum(cached_input_tokens)::bigint as cached_input_tokens,
      sum(gross_cost_usd) as gross_cost,
      percentile_cont(0.50) within group (order by latency_ms)
        filter (where status = 'completed') as p50,
      percentile_cont(0.95) within group (order by latency_ms)
        filter (where status = 'completed') as p95,
      max(latency_ms) filter (where status = 'completed') as max_latency,
      array_agg(distinct purpose order by purpose) as purposes,
      array_agg(distinct model order by model) filter (where model is not null) as models,
      array_agg(distinct provider order by provider) filter (where provider is not null) as providers,
      array_agg(distinct authentication_lane order by authentication_lane) as authentication_lanes
    from scoped
  )
  select
    p_since,
    p_until,
    p_environment,
    p_deployment_id,
    lower(p_commit_sha),
    case when cardinality(models) = 1 then models[1] else 'mixed' end,
    case when cardinality(providers) = 1 then providers[1] else 'mixed' end,
    case when cardinality(authentication_lanes) = 1 then authentication_lanes[1] else 'mixed' end,
    array[
      'tier:free',
      'feature:chat',
      'feature:creation-intent',
      'feature:answer-verifier',
      'feature:check-in'
    ]::text[],
    purposes,
    true,
    attempted,
    completed,
    failed,
    rate_limited,
    budget_rejected,
    usage_complete,
    cost_complete,
    case when usage_complete then input_tokens else null end,
    case when usage_complete then output_tokens else null end,
    case when usage_complete then cached_input_tokens else null end,
    case when cost_complete then gross_cost else null end,
    case
      when cost_complete and completed > 0 then gross_cost / completed
      else null
    end,
    case when cost_complete then 0::numeric else null end,
    p50,
    p95,
    max_latency,
    completed,
    false,
    false
  from rollup
  where attempted > 0;
$function$;

revoke execute on function public.claim_ai_gateway_cost_receipt(
  uuid, text, text, text, text, text, text, text
) from public, anon, authenticated;
revoke execute on function public.settle_ai_gateway_cost_receipt(
  uuid, text, text, text, text, bigint, bigint, bigint, numeric, integer, boolean, boolean
) from public, anon, authenticated;
revoke execute on function public.ai_gateway_provider_cost_aggregate(
  timestamptz, timestamptz, text, text, text
) from public, anon, authenticated;

grant execute on function public.claim_ai_gateway_cost_receipt(
  uuid, text, text, text, text, text, text, text
) to service_role;
grant execute on function public.settle_ai_gateway_cost_receipt(
  uuid, text, text, text, text, bigint, bigint, bigint, numeric, integer, boolean, boolean
) to service_role;
grant execute on function public.ai_gateway_provider_cost_aggregate(
  timestamptz, timestamptz, text, text, text
) to service_role;

comment on table public.ai_gateway_cost_receipts is
  'Content-free AI Gateway cost and usage receipts. Stores no customer identifiers, prompts, responses, filenames, URLs, credentials, or request bodies.';
comment on function public.ai_gateway_provider_cost_aggregate(
  timestamptz, timestamptz, text, text, text
) is
  'Service-role-only half-open release aggregate for Ask-Crump-only provider cost readiness. Returns no customer content or identifiers and fails closed through explicit completeness flags.';

commit;
