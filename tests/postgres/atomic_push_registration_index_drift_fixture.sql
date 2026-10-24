\set ON_ERROR_STOP on

drop index public.push_tokens_installation_id_idx;
create index push_tokens_installation_id_idx
  on public.push_tokens (user_id);
