\set ON_ERROR_STOP on

-- Simulate an unreviewed material definition change after the approved
-- hardening. The migration must fail closed rather than blessing it merely
-- because search_path is already empty.
alter function public.delete_own_account() immutable;
