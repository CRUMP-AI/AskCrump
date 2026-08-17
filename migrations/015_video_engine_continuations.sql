begin;

alter table public.media_jobs
  add column if not exists engine text not null default 'quick',
  add column if not exists operation_type text not null default 'generate',
  add column if not exists parent_job_id uuid references public.media_jobs(id) on delete set null,
  add column if not exists root_job_id uuid references public.media_jobs(id) on delete set null,
  add column if not exists sequence_index integer not null default 0,
  add column if not exists duration_seconds integer not null default 8,
  add column if not exists provider_asset_reference text,
  add column if not exists provider_asset_expires_at timestamptz,
  add column if not exists estimated_provider_cost_cents integer not null default 0;

alter table public.media_jobs
  drop constraint if exists media_jobs_engine_check,
  add constraint media_jobs_engine_check
    check (engine in ('quick','extendable','cinematic')),
  drop constraint if exists media_jobs_operation_type_check,
  add constraint media_jobs_operation_type_check
    check (operation_type in ('generate','extend')),
  drop constraint if exists media_jobs_sequence_index_check,
  add constraint media_jobs_sequence_index_check
    check (sequence_index >= 0 and sequence_index <= 20),
  drop constraint if exists media_jobs_duration_seconds_check,
  add constraint media_jobs_duration_seconds_check
    check (duration_seconds >= 1 and duration_seconds <= 148),
  drop constraint if exists media_jobs_estimated_provider_cost_cents_check,
  add constraint media_jobs_estimated_provider_cost_cents_check
    check (estimated_provider_cost_cents >= 0 and estimated_provider_cost_cents <= 100000);

create index if not exists media_jobs_root_sequence_idx
  on public.media_jobs(user_id, root_job_id, sequence_index);
create index if not exists media_jobs_parent_idx
  on public.media_jobs(parent_job_id)
  where parent_job_id is not null;

comment on column public.media_jobs.provider_asset_reference is
  'Server-only provider reference used for short-lived native video continuation. Never expose to clients.';
comment on column public.media_jobs.estimated_provider_cost_cents is
  'Conservative provider-cost estimate captured when the job is created for margin and spend observability.';

commit;
