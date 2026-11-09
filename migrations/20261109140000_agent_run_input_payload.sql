-- Agent runs: store the creation payload on the run row.
--
-- Execution must never accept caller-supplied input: a run executes
-- exactly what was stored for it. Approval-gated runs already freeze
-- their exact payload on the pending action; this column gives every
-- other run the same payload of record, captured at creation. The
-- column is server-only like the rest of the ledger (the API is the
-- only gateway; RLS stays enabled and anon/authenticated stay revoked
-- by the ledger migration).

begin;

alter table public.agent_runs
  add column if not exists input_payload jsonb not null default '{}'::jsonb;

alter table public.agent_runs
  drop constraint if exists agent_runs_input_payload_shape_check;

alter table public.agent_runs
  add constraint agent_runs_input_payload_shape_check
    check (
      jsonb_typeof(input_payload) = 'object'
      and octet_length(input_payload::text) <= 16000
    );

commit;
