-- Ask Crump 5.0.0
-- Private cloud files and generated artifacts.

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'crump-files',
  'crump-files',
  false,
  104857600,
  array[
    'image/jpeg','image/png','image/webp','image/gif','image/heic','image/heif',
    'application/pdf',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    'text/plain','text/markdown','text/csv','text/tab-separated-values',
    'application/json','text/html','application/rtf'
  ]
)
on conflict (id) do update set
  public = excluded.public,
  file_size_limit = excluded.file_size_limit,
  allowed_mime_types = excluded.allowed_mime_types;

create table if not exists public.user_files (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  chat_id uuid,
  message_id uuid,
  storage_path text not null unique,
  file_name text not null,
  mime_type text not null,
  size_bytes bigint not null default 0 check (size_bytes >= 0 and size_bytes <= 104857600),
  kind text not null default 'upload'
    check (kind in ('upload','generated_image','generated_document')),
  status text not null default 'pending'
    check (status in ('pending','ready','failed')),
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  deleted_at timestamptz
);

create index if not exists user_files_active_idx
  on public.user_files(user_id, created_at desc)
  where deleted_at is null;

create index if not exists user_files_chat_idx
  on public.user_files(user_id, chat_id, created_at)
  where deleted_at is null;

alter table public.user_files enable row level security;
revoke all on table public.user_files from anon, authenticated;
grant all on table public.user_files to service_role;
