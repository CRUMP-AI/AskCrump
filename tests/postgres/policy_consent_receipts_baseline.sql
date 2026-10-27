create role anon nologin;
create role authenticated nologin;
create role service_role nologin;

create table public.users (
  id uuid primary key,
  email text not null,
  is_guest boolean not null default false,
  is_verified boolean not null default false,
  registration_submitted_at timestamptz,
  terms_accepted_at timestamptz,
  terms_version text,
  updated_at timestamptz not null default pg_catalog.clock_timestamp(),
  deleted_at timestamptz
);

alter table public.users owner to postgres;
