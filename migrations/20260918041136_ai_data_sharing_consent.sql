-- Versioned, explicit permission required before personal data is shared with
-- a third-party AI provider. This is intentionally separate from Terms consent.

alter table public.users
  add column if not exists ai_data_sharing_consent_at timestamptz,
  add column if not exists ai_data_sharing_consent_version text,
  add column if not exists ai_data_sharing_consent_revoked_at timestamptz,
  add column if not exists ai_data_sharing_consent_updated_at timestamptz;

do $$
begin
  alter table public.users
    add constraint users_ai_data_sharing_consent_pair_check
    check (
      (
        ai_data_sharing_consent_at is null
        and ai_data_sharing_consent_version is null
        and ai_data_sharing_consent_revoked_at is null
      )
      or
      (
        ai_data_sharing_consent_at is not null
        and ai_data_sharing_consent_version is not null
        and char_length(ai_data_sharing_consent_version) between 1 and 64
        and (
          ai_data_sharing_consent_revoked_at is null
          or ai_data_sharing_consent_revoked_at >= ai_data_sharing_consent_at
        )
      )
    );
exception
  when duplicate_object then null;
end
$$;

comment on column public.users.ai_data_sharing_consent_at is
  'Time the account explicitly allowed prompts and selected files to be sent to configured third-party AI providers.';
comment on column public.users.ai_data_sharing_consent_version is
  'Disclosure version accepted separately from Terms. Null means permission was never granted.';
comment on column public.users.ai_data_sharing_consent_revoked_at is
  'Time the user withdrew AI data-sharing permission. Acceptance history is preserved for auditability.';
comment on column public.users.ai_data_sharing_consent_updated_at is
  'Last acceptance or withdrawal update time for the AI data-sharing permission.';
