-- Supabase default privileges grant service_role broad access to newly created
-- tables. Narrow the live Crump Code grants so lifecycle events remain
-- append-only and approval decisions cannot be erased.

begin;

revoke all on table public.code_tasks from service_role;
revoke all on table public.code_task_events from service_role;
revoke all on table public.code_task_approvals from service_role;
revoke all on sequence public.code_task_events_id_seq from service_role;

grant all on table public.code_tasks to service_role;
grant select, insert on table public.code_task_events to service_role;
grant select, insert, update on table public.code_task_approvals to service_role;
grant usage, select on sequence public.code_task_events_id_seq to service_role;

commit;
