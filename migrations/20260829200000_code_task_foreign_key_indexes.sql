-- Keep cascading project and account cleanup bounded as Crump Code audit
-- history grows. The task-first indexes serve task history reads, while these
-- indexes cover the independent user_id and project_id foreign keys.

begin;

create index if not exists code_task_events_user_idx
  on public.code_task_events(user_id);

create index if not exists code_task_events_project_idx
  on public.code_task_events(project_id);

create index if not exists code_task_approvals_user_idx
  on public.code_task_approvals(user_id);

create index if not exists code_task_approvals_project_idx
  on public.code_task_approvals(project_id);

commit;
