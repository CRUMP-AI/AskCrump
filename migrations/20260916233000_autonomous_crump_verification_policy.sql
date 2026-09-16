-- Autonomous Crump verification authority is captured once with the prepared
-- task. Repository tests and check scripts are executable repository content;
-- they must never become authorized merely because a model requested them.

begin;

alter table public.code_tasks
  add column if not exists verification_policy text not null default 'syntax_only';

alter table public.code_tasks
  drop constraint if exists code_tasks_verification_policy_check;

alter table public.code_tasks
  add constraint code_tasks_verification_policy_check
  check (verification_policy in ('syntax_only', 'project_checks'));

create or replace function public.keep_code_task_verification_policy_immutable()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  if new.verification_policy is distinct from old.verification_policy then
    raise exception 'Autonomous Crump verification policy is immutable after task preparation'
      using errcode = '23514';
  end if;
  return new;
end;
$$;

revoke all on function public.keep_code_task_verification_policy_immutable()
  from public, anon, authenticated, service_role;

drop trigger if exists keep_code_task_verification_policy_immutable
  on public.code_tasks;

create trigger keep_code_task_verification_policy_immutable
before update of verification_policy on public.code_tasks
for each row execute function public.keep_code_task_verification_policy_immutable();

comment on column public.code_tasks.verification_policy is
  'Immutable prepared-task choice: syntax_only blocks repository-owned executable checks; project_checks records the owner choice permitting bounded checks and redacted model-visible output.';

comment on function public.keep_code_task_verification_policy_immutable() is
  'Prevents a prepared Autonomous Crump task from gaining or losing repository-check authority after review.';

commit;
