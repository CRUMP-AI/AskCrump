\set ON_ERROR_STOP on

-- The production Supabase project uses pg_cron. The generic PostgreSQL CI
-- image does not ship that extension, so this narrow stub models only the
-- named scheduling contract exercised by the migration and its reapply gate.
create schema if not exists cron;

create table if not exists cron.job (
  jobid bigint generated always as identity primary key,
  schedule text not null,
  command text not null,
  nodename text not null,
  nodeport integer not null,
  database text not null,
  username text not null,
  active boolean not null,
  jobname text not null,
  unique (jobname, username)
);

create or replace function cron.schedule(
  p_job_name text,
  p_schedule text,
  p_command text
)
returns bigint
language plpgsql
as $function$
declare
  v_job_id bigint;
begin
  insert into cron.job (
    schedule,
    command,
    nodename,
    nodeport,
    database,
    username,
    active,
    jobname
  ) values (
    p_schedule,
    p_command,
    'localhost',
    current_setting('port')::integer,
    current_database(),
    current_user,
    true,
    p_job_name
  )
  on conflict (jobname, username) do update
    set schedule = excluded.schedule,
        command = excluded.command,
        database = excluded.database
  returning jobid into v_job_id;

  return v_job_id;
end;
$function$;
