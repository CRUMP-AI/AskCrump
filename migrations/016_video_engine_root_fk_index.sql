begin;

create index if not exists media_jobs_root_job_id_idx
  on public.media_jobs(root_job_id)
  where root_job_id is not null;

commit;
