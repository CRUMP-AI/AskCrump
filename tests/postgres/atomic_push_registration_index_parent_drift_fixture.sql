\set ON_ERROR_STOP on

drop index public.push_tokens_installation_id_idx;
create table public.push_token_index_decoy (
  installation_id text not null
);
create index push_tokens_installation_id_idx
  on public.push_token_index_decoy (installation_id);
