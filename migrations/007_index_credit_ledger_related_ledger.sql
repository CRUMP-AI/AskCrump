-- Ask Crump release hardening
-- Mirrors the production migration applied 2026-08-11 as
-- Supabase migration: index_credit_ledger_related_ledger.

begin;

create index if not exists credit_ledger_related_ledger_idx
  on public.credit_ledger (related_ledger_id)
  where related_ledger_id is not null;

commit;
