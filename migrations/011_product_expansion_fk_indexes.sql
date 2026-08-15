-- Ask Crump 5.3 product-expansion foreign-key index hardening.
-- Mirrors the FK indexes already applied to production Supabase on 2026-08-14.
-- These indexes make cascade/delete and relationship lookups scale cleanly.

begin;

create index if not exists project_files_file_id_idx
  on public.project_files(file_id);

create index if not exists project_context_project_id_idx
  on public.project_context(project_id);

create index if not exists manuscripts_project_id_idx
  on public.manuscripts(project_id);

create index if not exists manuscript_sections_manuscript_id_idx
  on public.manuscript_sections(manuscript_id);

create index if not exists media_jobs_project_id_idx
  on public.media_jobs(project_id);

create index if not exists media_jobs_file_id_idx
  on public.media_jobs(file_id);

commit;