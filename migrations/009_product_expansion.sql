begin;

-- Ask Crump 5.3.0
-- Projects, manuscripts, asynchronous generated video, and expanded private artifacts.

-- Extend the existing private storage bucket for generated video and Kindle EPUB exports.
update storage.buckets
set allowed_mime_types = array[
  'image/jpeg','image/png','image/webp','image/gif','image/heic','image/heif',
  'video/mp4','video/webm',
  'application/pdf','application/epub+zip',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  'text/plain','text/markdown','text/csv','text/tab-separated-values',
  'application/json','text/html','application/rtf'
]
where id = 'crump-files';

alter table public.user_files drop constraint if exists user_files_kind_check;
alter table public.user_files
  add constraint user_files_kind_check
  check (kind in (
    'upload','generated_image','generated_document','generated_video',
    'manuscript_export','project_asset'
  ));

create table if not exists public.projects (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  name text not null check (char_length(name) between 1 and 100),
  description text not null default '',
  instructions text not null default '',
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  archived_at timestamptz
);

create index if not exists projects_active_user_idx
  on public.projects(user_id, updated_at desc)
  where archived_at is null;

create table if not exists public.project_chats (
  project_id uuid not null references public.projects(id) on delete cascade,
  user_id uuid not null references public.users(id) on delete cascade,
  chat_id uuid not null,
  created_at timestamptz not null default now(),
  primary key (project_id, chat_id)
);
create index if not exists project_chats_user_chat_idx
  on public.project_chats(user_id, chat_id);

create table if not exists public.project_files (
  project_id uuid not null references public.projects(id) on delete cascade,
  user_id uuid not null references public.users(id) on delete cascade,
  file_id uuid not null references public.user_files(id) on delete cascade,
  role text not null default 'asset',
  created_at timestamptz not null default now(),
  primary key (project_id, file_id)
);
create index if not exists project_files_user_idx
  on public.project_files(user_id, project_id, created_at desc);

create table if not exists public.project_context (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references public.projects(id) on delete cascade,
  user_id uuid not null references public.users(id) on delete cascade,
  kind text not null default 'note',
  label text not null default '',
  content text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists project_context_project_idx
  on public.project_context(user_id, project_id, updated_at desc);

create table if not exists public.manuscripts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  project_id uuid not null references public.projects(id) on delete cascade,
  title text not null,
  subtitle text not null default '',
  author_name text not null default '',
  trim_code text not null default '6x9',
  trim_width numeric(6,3) not null default 6.0,
  trim_height numeric(6,3) not null default 9.0,
  bleed boolean not null default false,
  status text not null default 'draft'
    check (status in ('draft','revising','final')),
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  archived_at timestamptz
);
create index if not exists manuscripts_project_idx
  on public.manuscripts(user_id, project_id, updated_at desc)
  where archived_at is null;

create table if not exists public.manuscript_sections (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  manuscript_id uuid not null references public.manuscripts(id) on delete cascade,
  section_type text not null default 'chapter'
    check (section_type in ('frontmatter','chapter','scene','backmatter')),
  title text not null,
  position integer not null default 1 check (position > 0),
  content text not null default '',
  summary text not null default '',
  word_count integer not null default 0 check (word_count >= 0),
  status text not null default 'outline'
    check (status in ('outline','draft','revised','final')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists manuscript_sections_order_idx
  on public.manuscript_sections(user_id, manuscript_id, position);

create table if not exists public.media_jobs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  project_id uuid references public.projects(id) on delete set null,
  kind text not null check (kind in ('video')),
  provider text not null,
  provider_job_id text not null,
  idempotency_key text,
  status text not null default 'queued'
    check (status in ('queued','processing','ready','failed')),
  prompt text not null,
  model text not null,
  aspect_ratio text not null default '16:9'
    check (aspect_ratio in ('16:9','9:16')),
  resolution text not null default '720p'
    check (resolution in ('720p','1080p')),
  file_id uuid references public.user_files(id) on delete set null,
  error_message text,
  billing_receipt jsonb not null default '{}'::jsonb,
  billing_refunded boolean not null default false,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists media_jobs_user_status_idx
  on public.media_jobs(user_id, status, created_at desc);
create unique index if not exists media_jobs_user_idempotency_idx
  on public.media_jobs(user_id, idempotency_key)
  where idempotency_key is not null;

-- The browser never queries these tables directly. Ask Crump's authenticated backend
-- owns access through the Supabase service role, matching the existing production model.
alter table public.projects enable row level security;
alter table public.project_chats enable row level security;
alter table public.project_files enable row level security;
alter table public.project_context enable row level security;
alter table public.manuscripts enable row level security;
alter table public.manuscript_sections enable row level security;
alter table public.media_jobs enable row level security;

revoke all on table public.projects from anon, authenticated;
revoke all on table public.project_chats from anon, authenticated;
revoke all on table public.project_files from anon, authenticated;
revoke all on table public.project_context from anon, authenticated;
revoke all on table public.manuscripts from anon, authenticated;
revoke all on table public.manuscript_sections from anon, authenticated;
revoke all on table public.media_jobs from anon, authenticated;

grant all on table public.projects to service_role;
grant all on table public.project_chats to service_role;
grant all on table public.project_files to service_role;
grant all on table public.project_context to service_role;
grant all on table public.manuscripts to service_role;
grant all on table public.manuscript_sections to service_role;
grant all on table public.media_jobs to service_role;

commit;
