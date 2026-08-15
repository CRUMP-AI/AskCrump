-- Ask Crump production hardening source record.
-- This migration mirrors the duplicate-index / redundant-constraint cleanup already
-- applied to production Supabase on 2026-08-14.
--
-- Keep the canonical indexes and constraint defined by migrations/001_python_backend.sql.

begin;

-- sessions(device_id) is already covered by the canonical unique device/session key.
drop index if exists public.idx_sessions_device_id;
drop index if exists public.sessions_device_id_idx;

-- Keep canonical sessions_expiry_idx.
drop index if exists public.sessions_expires_at_idx;

-- Keep canonical user_chats_sync_idx.
drop index if exists public.user_chats_user_updated_idx;

-- Keep canonical user_chats_user_chat_unique.
alter table public.user_chats
  drop constraint if exists user_chats_user_chat_id_unique;

commit;