#!/usr/bin/env bash
set -euo pipefail

token_hash="$(printf 'e%.0s' {1..64})"
password_a='$argon2id$concurrent-winner-a-password-hash'
password_b='$argon2id$concurrent-winner-b-password-hash'
user_id='30000000-0000-4000-8000-000000000005'

psql -X --set=ON_ERROR_STOP=1 <<'SQL'
insert into public.users (
  id, email, password_hash, is_verified, is_guest,
  password_reset_token_hash, password_reset_expires,
  created_at, updated_at, registration_environment,
  registration_submitted_at
) values (
  '30000000-0000-4000-8000-000000000005',
  'concurrent@example.test',
  '$argon2id$concurrent-old-password-hash',
  false,
  true,
  repeat('e', 64),
  pg_catalog.clock_timestamp() + interval '1 hour',
  pg_catalog.clock_timestamp() - interval '1 hour',
  pg_catalog.clock_timestamp() - interval '5 minutes',
  'production',
  pg_catalog.clock_timestamp() - interval '30 minutes'
);

insert into public.sessions (id, user_id, token_hash, expires_at)
values (
  '31000000-0000-4000-8000-000000000005',
  '30000000-0000-4000-8000-000000000005',
  repeat('5', 64),
  pg_catalog.clock_timestamp() + interval '1 day'
);

create or replace function public.delay_test_password_reset_update()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  if old.id = '30000000-0000-4000-8000-000000000005'::uuid
     and old.password_reset_token_hash is not null
     and new.password_reset_token_hash is null then
    perform pg_catalog.pg_sleep(1);
  end if;
  return new;
end;
$$;

create trigger delay_test_password_reset_update
before update on public.users
for each row
execute function public.delay_test_password_reset_update();
SQL

result_dir="$(mktemp -d)"
trap 'rm -rf -- "$result_dir"' EXIT

psql -X -qAt --set=ON_ERROR_STOP=1 \
  -c "set role service_role; select reset_applied from public.consume_password_reset_v1('$token_hash', '$password_a');" \
  >"$result_dir/a" &
pid_a=$!
sleep 0.1
psql -X -qAt --set=ON_ERROR_STOP=1 \
  -c "set role service_role; select reset_applied from public.consume_password_reset_v1('$token_hash', '$password_b');" \
  >"$result_dir/b" &
pid_b=$!

wait "$pid_a"
wait "$pid_b"

result_a="$(tr -d '\r\n[:space:]' <"$result_dir/a")"
result_b="$(tr -d '\r\n[:space:]' <"$result_dir/b")"

if [[ "$result_a" == "t" && "$result_b" == "f" ]]; then
  winning_password="$password_a"
elif [[ "$result_a" == "f" && "$result_b" == "t" ]]; then
  winning_password="$password_b"
else
  echo "Expected exactly one reset winner; got A=$result_a B=$result_b" >&2
  exit 1
fi

final_state="$(psql -X -qAt --set=ON_ERROR_STOP=1 -c "
select
  account.password_hash = '$winning_password'
  and account.password_reset_token_hash is null
  and account.password_reset_expires is null
  and account.is_verified is true
  and account.is_guest is false
  and account.email_verified_at is not null
  and session.revoked_at is not null
from public.users as account
join public.sessions as session on session.user_id = account.id
where account.id = '$user_id';
")"

if [[ "$(printf '%s' "$final_state" | tr -d '\r\n[:space:]')" != "t" ]]; then
  echo "Concurrent winner did not define the complete committed state." >&2
  exit 1
fi

psql -X --set=ON_ERROR_STOP=1 <<'SQL'
drop trigger delay_test_password_reset_update on public.users;
drop function public.delay_test_password_reset_update();
SQL

# Login-first/reset-second: the login holds the shared user serialization row,
# then reset commits last and must revoke the session the old password issued.
psql -X --set=ON_ERROR_STOP=1 <<'SQL'
insert into public.users (
  id, email, password_hash, is_verified, is_guest,
  password_reset_token_hash, password_reset_expires,
  created_at, updated_at, registration_environment, registration_submitted_at
) values (
  '50000000-0000-4000-8000-000000000001', 'login-first-race@example.test',
  '$argon2id$login-first-old-password-hash', true, false,
  encode(digest('login-first-reset-token', 'sha256'), 'hex'),
  clock_timestamp() + interval '1 hour', clock_timestamp() - interval '1 day',
  clock_timestamp() - interval '1 hour', 'production',
  clock_timestamp() - interval '1 day'
);
create or replace function public.delay_test_login_first()
returns trigger language plpgsql security invoker set search_path = '' as $$
begin
  if old.id = '50000000-0000-4000-8000-000000000001'::uuid
     and old.last_login is null and new.last_login is not null then
    perform pg_catalog.pg_sleep(1);
  end if;
  return new;
end;
$$;
create trigger delay_test_login_first before update on public.users
for each row execute function public.delay_test_login_first();
SQL

psql -X -qAt --set=ON_ERROR_STOP=1 -c "
set role service_role;
select login_applied from public.finalize_password_login_v1(
  '50000000-0000-4000-8000-000000000001',
  '\$argon2id\$login-first-old-password-hash', null,
  '51000000-0000-4000-8000-000000000001',
  encode(digest('login-first-session', 'sha256'), 'hex'),
  clock_timestamp() + interval '1 day', null, 'Desktop', 'web',
  '{}'::jsonb, '127.0.0.1', 'pytest'
);" >"$result_dir/login-first" &
login_first_pid=$!
sleep 0.1
psql -X -qAt --set=ON_ERROR_STOP=1 -c "
set role service_role;
select reset_applied from public.consume_password_reset_v1(
  encode(digest('login-first-reset-token', 'sha256'), 'hex'),
  '\$argon2id\$login-first-reset-winner-hash'
);" >"$result_dir/login-first-reset" &
login_first_reset_pid=$!
wait "$login_first_pid"
wait "$login_first_reset_pid"

if [[ "$(tr -d '\r\n[:space:]' <"$result_dir/login-first")" != "t" ]] \
   || [[ "$(tr -d '\r\n[:space:]' <"$result_dir/login-first-reset")" != "t" ]]; then
  echo "Login-first/reset-second did not produce two ordered winners." >&2
  exit 1
fi

login_first_state="$(psql -X -qAt --set=ON_ERROR_STOP=1 -c "
select account.password_hash = '\$argon2id\$login-first-reset-winner-hash'
  and account.password_reset_token_hash is null
  and session.revoked_at is not null
from public.users as account
join public.sessions as session on session.user_id = account.id
where account.id = '50000000-0000-4000-8000-000000000001';
")"
if [[ "$(printf '%s' "$login_first_state" | tr -d '\r\n[:space:]')" != "t" ]]; then
  echo "Reset did not win after an old-password login committed first." >&2
  exit 1
fi
psql -X --set=ON_ERROR_STOP=1 -c "drop trigger delay_test_login_first on public.users; drop function public.delay_test_login_first();"

# Reset-first/login-second: a stale login waits on the reset's user lock, then
# its exact-hash compare fails before either the new-session or device-upsert path.
psql -X --set=ON_ERROR_STOP=1 <<'SQL'
insert into public.users (
  id, email, password_hash, is_verified, is_guest,
  password_reset_token_hash, password_reset_expires,
  created_at, updated_at, registration_environment, registration_submitted_at
) values (
  '50000000-0000-4000-8000-000000000002', 'reset-first-race@example.test',
  '$argon2id$reset-first-old-password-hash', true, false,
  encode(digest('reset-first-reset-token', 'sha256'), 'hex'),
  clock_timestamp() + interval '1 hour', clock_timestamp() - interval '1 day',
  clock_timestamp() - interval '1 hour', 'production',
  clock_timestamp() - interval '1 day'
);
insert into public.sessions (
  id, user_id, token_hash, device_id, expires_at
) values (
  '51000000-0000-4000-8000-000000000002',
  '50000000-0000-4000-8000-000000000002',
  encode(digest('reset-first-existing-session', 'sha256'), 'hex'),
  'reset-first-device', clock_timestamp() + interval '1 day'
);
create or replace function public.delay_test_reset_first()
returns trigger language plpgsql security invoker set search_path = '' as $$
begin
  if old.id = '50000000-0000-4000-8000-000000000002'::uuid
     and old.password_reset_token_hash is not null
     and new.password_reset_token_hash is null then
    perform pg_catalog.pg_sleep(1);
  end if;
  return new;
end;
$$;
create trigger delay_test_reset_first before update on public.users
for each row execute function public.delay_test_reset_first();
SQL

psql -X -qAt --set=ON_ERROR_STOP=1 -c "
set role service_role;
select reset_applied from public.consume_password_reset_v1(
  encode(digest('reset-first-reset-token', 'sha256'), 'hex'),
  '\$argon2id\$reset-first-new-password-hash'
);" >"$result_dir/reset-first" &
reset_first_pid=$!
sleep 0.1
psql -X -qAt --set=ON_ERROR_STOP=1 -c "
set role service_role;
select login_applied from public.finalize_password_login_v1(
  '50000000-0000-4000-8000-000000000002',
  '\$argon2id\$reset-first-old-password-hash', null,
  '51000000-0000-4000-8000-000000000003',
  encode(digest('reset-first-stale-session', 'sha256'), 'hex'),
  clock_timestamp() + interval '1 day', 'reset-first-device', 'Desktop', 'web',
  '{}'::jsonb, '127.0.0.1', 'pytest'
);" >"$result_dir/reset-first-login" &
reset_first_login_pid=$!
wait "$reset_first_pid"
wait "$reset_first_login_pid"

if [[ "$(tr -d '\r\n[:space:]' <"$result_dir/reset-first")" != "t" ]] \
   || [[ "$(tr -d '\r\n[:space:]' <"$result_dir/reset-first-login")" != "f" ]]; then
  echo "Reset-first/login-second did not reject the stale login." >&2
  exit 1
fi

reset_first_state="$(psql -X -qAt --set=ON_ERROR_STOP=1 -c "
select account.password_hash = '\$argon2id\$reset-first-new-password-hash'
  and account.password_reset_token_hash is null
  and count(session.*) = 1
  and bool_and(
    session.token_hash = encode(
      digest('reset-first-existing-session', 'sha256'), 'hex'
    )
  )
  and bool_and(session.revoked_at is not null)
from public.users as account
left join public.sessions as session on session.user_id = account.id
where account.id = '50000000-0000-4000-8000-000000000002'
group by account.password_hash, account.password_reset_token_hash;
")"
if [[ "$(printf '%s' "$reset_first_state" | tr -d '\r\n[:space:]')" != "t" ]]; then
  echo "Stale login changed reset state or rotated the existing device session." >&2
  exit 1
fi
psql -X --set=ON_ERROR_STOP=1 -c "drop trigger delay_test_reset_first on public.users; drop function public.delay_test_reset_first();"

# Verification-first/reset-second: verification holds the shared user lock
# through session mint, then reset commits last and revokes that session.
psql -X --set=ON_ERROR_STOP=1 <<'SQL'
insert into public.users (
  id, email, password_hash, is_verified, is_guest,
  verification_token_hash, verification_token_expires,
  password_reset_token_hash, password_reset_expires,
  created_at, updated_at, registration_environment, registration_submitted_at
) values (
  '50000000-0000-4000-8000-000000000010',
  'verification-first-race@example.test',
  '$argon2id$verification-first-old-password-hash', false, false,
  repeat('a', 64), clock_timestamp() + interval '1 hour',
  encode(digest('verification-first-reset-token', 'sha256'), 'hex'),
  clock_timestamp() + interval '1 hour', clock_timestamp() - interval '1 day',
  clock_timestamp() - interval '1 hour', 'production',
  clock_timestamp() - interval '1 day'
);
create or replace function public.delay_test_verification_first()
returns trigger language plpgsql security invoker set search_path = '' as $$
begin
  if old.id = '50000000-0000-4000-8000-000000000010'::uuid
     and old.is_verified is false and new.is_verified is true then
    perform pg_catalog.pg_sleep(1);
  end if;
  return new;
end;
$$;
create trigger delay_test_verification_first before update on public.users
for each row execute function public.delay_test_verification_first();
SQL

psql -X -qAt --set=ON_ERROR_STOP=1 -c "
set role service_role;
select verification_applied
from public.verify_registered_and_create_session_v1(
  '50000000-0000-4000-8000-000000000010', repeat('a', 64),
  '51000000-0000-4000-8000-000000000010',
  encode(digest('verification-first-session', 'sha256'), 'hex'),
  clock_timestamp() + interval '1 day', null, 'Verified link', 'web',
  '{}'::jsonb, '127.0.0.1', 'pytest'
);" >"$result_dir/verification-first" &
verification_first_pid=$!
sleep 0.1
psql -X -qAt --set=ON_ERROR_STOP=1 -c "
set role service_role;
select reset_applied from public.consume_password_reset_v1(
  encode(digest('verification-first-reset-token', 'sha256'), 'hex'),
  '\$argon2id\$verification-first-reset-winner-hash'
);" >"$result_dir/verification-first-reset" &
verification_first_reset_pid=$!
wait "$verification_first_pid"
wait "$verification_first_reset_pid"

if [[ "$(tr -d '\r\n[:space:]' <"$result_dir/verification-first")" != "t" ]] \
   || [[ "$(tr -d '\r\n[:space:]' <"$result_dir/verification-first-reset")" != "t" ]]; then
  echo "Verification-first/reset-second did not produce two ordered winners." >&2
  exit 1
fi

verification_first_state="$(psql -X -qAt --set=ON_ERROR_STOP=1 -c "
select account.password_hash = '\$argon2id\$verification-first-reset-winner-hash'
  and account.verification_token_hash is null
  and account.password_reset_token_hash is null
  and account.email_verified_at is not null
  and count(session.*) = 1
  and bool_and(session.revoked_at is not null)
from public.users as account
left join public.sessions as session on session.user_id = account.id
where account.id = '50000000-0000-4000-8000-000000000010'
group by account.password_hash, account.verification_token_hash,
  account.password_reset_token_hash, account.email_verified_at;
")"
if [[ "$(printf '%s' "$verification_first_state" | tr -d '\r\n[:space:]')" != "t" ]]; then
  echo "Reset did not revoke the session committed by earlier verification." >&2
  exit 1
fi
psql -X --set=ON_ERROR_STOP=1 -c "drop trigger delay_test_verification_first on public.users; drop function public.delay_test_verification_first();"

# Reset-first/verification-second: reset clears the token and revokes the old
# device session before the stale verification can recheck under the row lock.
psql -X --set=ON_ERROR_STOP=1 <<'SQL'
insert into public.users (
  id, email, password_hash, is_verified, is_guest,
  verification_token_hash, verification_token_expires,
  password_reset_token_hash, password_reset_expires,
  created_at, updated_at, registration_environment, registration_submitted_at
) values (
  '50000000-0000-4000-8000-000000000011',
  'reset-before-verification@example.test',
  '$argon2id$reset-before-verification-old-hash', false, false,
  repeat('b', 64), clock_timestamp() + interval '1 hour',
  encode(digest('reset-before-verification-token', 'sha256'), 'hex'),
  clock_timestamp() + interval '1 hour', clock_timestamp() - interval '1 day',
  clock_timestamp() - interval '1 hour', 'production',
  clock_timestamp() - interval '1 day'
);
insert into public.sessions (
  id, user_id, token_hash, device_id, expires_at
) values (
  '51000000-0000-4000-8000-000000000011',
  '50000000-0000-4000-8000-000000000011',
  encode(digest('reset-before-verification-existing-session', 'sha256'), 'hex'),
  'reset-before-verification-device', clock_timestamp() + interval '1 day'
);
create or replace function public.delay_test_reset_before_verification()
returns trigger language plpgsql security invoker set search_path = '' as $$
begin
  if old.id = '50000000-0000-4000-8000-000000000011'::uuid
     and old.password_reset_token_hash is not null
     and new.password_reset_token_hash is null then
    perform pg_catalog.pg_sleep(1);
  end if;
  return new;
end;
$$;
create trigger delay_test_reset_before_verification before update on public.users
for each row execute function public.delay_test_reset_before_verification();
SQL

psql -X -qAt --set=ON_ERROR_STOP=1 -c "
set role service_role;
select reset_applied from public.consume_password_reset_v1(
  encode(digest('reset-before-verification-token', 'sha256'), 'hex'),
  '\$argon2id\$reset-before-verification-new-hash'
);" >"$result_dir/reset-before-verification" &
reset_before_verification_pid=$!
sleep 0.1
psql -X -qAt --set=ON_ERROR_STOP=1 -c "
set role service_role;
select verification_applied
from public.verify_registered_and_create_session_v1(
  '50000000-0000-4000-8000-000000000011', repeat('b', 64),
  '51000000-0000-4000-8000-000000000012',
  encode(digest('reset-before-verification-stale-session', 'sha256'), 'hex'),
  clock_timestamp() + interval '1 day', 'reset-before-verification-device',
  'Verified link', 'web', '{}'::jsonb, '127.0.0.1', 'pytest'
);" >"$result_dir/reset-before-verification-stale" &
stale_verification_pid=$!
wait "$reset_before_verification_pid"
wait "$stale_verification_pid"

if [[ "$(tr -d '\r\n[:space:]' <"$result_dir/reset-before-verification")" != "t" ]] \
   || [[ "$(tr -d '\r\n[:space:]' <"$result_dir/reset-before-verification-stale")" != "f" ]]; then
  echo "Reset-first/verification-second did not reject stale verification." >&2
  exit 1
fi

reset_before_verification_state="$(psql -X -qAt --set=ON_ERROR_STOP=1 -c "
select account.password_hash = '\$argon2id\$reset-before-verification-new-hash'
  and account.verification_token_hash is null
  and count(session.*) = 1
  and bool_and(
    session.id = '51000000-0000-4000-8000-000000000011'::uuid
    and session.token_hash = encode(
      digest('reset-before-verification-existing-session', 'sha256'), 'hex'
    )
    and session.revoked_at is not null
  )
from public.users as account
left join public.sessions as session on session.user_id = account.id
where account.id = '50000000-0000-4000-8000-000000000011'
group by account.password_hash, account.verification_token_hash;
")"
if [[ "$(printf '%s' "$reset_before_verification_state" | tr -d '\r\n[:space:]')" != "t" ]]; then
  echo "Stale verification changed the reset winner or rotated its device row." >&2
  exit 1
fi
psql -X --set=ON_ERROR_STOP=1 -c "drop trigger delay_test_reset_before_verification on public.users; drop function public.delay_test_reset_before_verification();"

# Two concurrent clicks may observe the same bearer in the application, but the
# locked database transition grants exactly one session.
psql -X --set=ON_ERROR_STOP=1 <<'SQL'
insert into public.users (
  id, email, password_hash, is_verified, is_guest,
  verification_token_hash, verification_token_expires,
  created_at, updated_at, registration_environment, registration_submitted_at
) values (
  '50000000-0000-4000-8000-000000000012',
  'concurrent-verification@example.test',
  '$argon2id$concurrent-verification-hash', false, false,
  repeat('c', 64), clock_timestamp() + interval '1 hour',
  clock_timestamp() - interval '1 day', clock_timestamp() - interval '1 hour',
  'production', clock_timestamp() - interval '1 day'
);
create or replace function public.delay_test_concurrent_verification()
returns trigger language plpgsql security invoker set search_path = '' as $$
begin
  if old.id = '50000000-0000-4000-8000-000000000012'::uuid
     and old.is_verified is false and new.is_verified is true then
    perform pg_catalog.pg_sleep(1);
  end if;
  return new;
end;
$$;
create trigger delay_test_concurrent_verification before update on public.users
for each row execute function public.delay_test_concurrent_verification();
SQL

psql -X -qAt --set=ON_ERROR_STOP=1 -c "
set role service_role;
select verification_applied
from public.verify_registered_and_create_session_v1(
  '50000000-0000-4000-8000-000000000012', repeat('c', 64),
  '51000000-0000-4000-8000-000000000013',
  encode(digest('concurrent-verification-a', 'sha256'), 'hex'),
  clock_timestamp() + interval '1 day', null, 'Verified link', 'web',
  '{}'::jsonb, '127.0.0.1', 'pytest'
);" >"$result_dir/concurrent-verification-a" &
concurrent_verification_a_pid=$!
sleep 0.1
psql -X -qAt --set=ON_ERROR_STOP=1 -c "
set role service_role;
select verification_applied
from public.verify_registered_and_create_session_v1(
  '50000000-0000-4000-8000-000000000012', repeat('c', 64),
  '51000000-0000-4000-8000-000000000014',
  encode(digest('concurrent-verification-b', 'sha256'), 'hex'),
  clock_timestamp() + interval '1 day', null, 'Verified link', 'web',
  '{}'::jsonb, '127.0.0.1', 'pytest'
);" >"$result_dir/concurrent-verification-b" &
concurrent_verification_b_pid=$!
wait "$concurrent_verification_a_pid"
wait "$concurrent_verification_b_pid"

concurrent_verification_a="$(tr -d '\r\n[:space:]' <"$result_dir/concurrent-verification-a")"
concurrent_verification_b="$(tr -d '\r\n[:space:]' <"$result_dir/concurrent-verification-b")"
if ! { [[ "$concurrent_verification_a" == "t" && "$concurrent_verification_b" == "f" ]] \
  || [[ "$concurrent_verification_a" == "f" && "$concurrent_verification_b" == "t" ]]; }; then
  echo "Expected exactly one concurrent verification winner; got A=$concurrent_verification_a B=$concurrent_verification_b" >&2
  exit 1
fi

concurrent_verification_count="$(psql -X -qAt --set=ON_ERROR_STOP=1 -c "
select count(*) = 1 and bool_and(revoked_at is null)
from public.sessions
where user_id = '50000000-0000-4000-8000-000000000012';
")"
if [[ "$(printf '%s' "$concurrent_verification_count" | tr -d '\r\n[:space:]')" != "t" ]]; then
  echo "Concurrent verification created more than one live session." >&2
  exit 1
fi
psql -X --set=ON_ERROR_STOP=1 -c "drop trigger delay_test_concurrent_verification on public.users; drop function public.delay_test_concurrent_verification();"

# Two stale legacy-hash logins may both verify in Python, but only the first
# exact-hash compare may upgrade the password and issue a session.
psql -X --set=ON_ERROR_STOP=1 <<'SQL'
insert into public.users (
  id, email, password_hash, is_verified, is_guest,
  created_at, updated_at, registration_environment, registration_submitted_at
) values (
  '50000000-0000-4000-8000-000000000003', 'legacy-race@example.test',
  '$2b$12$legacy-race-old-password-hash', true, false,
  clock_timestamp() - interval '1 day', clock_timestamp() - interval '1 hour',
  'production', clock_timestamp() - interval '1 day'
);
create or replace function public.delay_test_legacy_login()
returns trigger language plpgsql security invoker set search_path = '' as $$
begin
  if old.id = '50000000-0000-4000-8000-000000000003'::uuid
     and old.last_login is null and new.last_login is not null then
    perform pg_catalog.pg_sleep(1);
  end if;
  return new;
end;
$$;
create trigger delay_test_legacy_login before update on public.users
for each row execute function public.delay_test_legacy_login();
SQL

psql -X -qAt --set=ON_ERROR_STOP=1 -c "
set role service_role;
select login_applied from public.finalize_password_login_v1(
  '50000000-0000-4000-8000-000000000003',
  '\$2b\$12\$legacy-race-old-password-hash', '\$argon2id\$legacy-race-upgrade-a',
  '51000000-0000-4000-8000-000000000004',
  encode(digest('legacy-session-a', 'sha256'), 'hex'),
  clock_timestamp() + interval '1 day', null, 'Desktop', 'web',
  '{}'::jsonb, '127.0.0.1', 'pytest'
);" >"$result_dir/legacy-a" &
legacy_a_pid=$!
sleep 0.1
psql -X -qAt --set=ON_ERROR_STOP=1 -c "
set role service_role;
select login_applied from public.finalize_password_login_v1(
  '50000000-0000-4000-8000-000000000003',
  '\$2b\$12\$legacy-race-old-password-hash', '\$argon2id\$legacy-race-upgrade-b',
  '51000000-0000-4000-8000-000000000005',
  encode(digest('legacy-session-b', 'sha256'), 'hex'),
  clock_timestamp() + interval '1 day', null, 'Desktop', 'web',
  '{}'::jsonb, '127.0.0.1', 'pytest'
);" >"$result_dir/legacy-b" &
legacy_b_pid=$!
wait "$legacy_a_pid"
wait "$legacy_b_pid"

legacy_a="$(tr -d '\r\n[:space:]' <"$result_dir/legacy-a")"
legacy_b="$(tr -d '\r\n[:space:]' <"$result_dir/legacy-b")"
if [[ "$legacy_a" == "t" && "$legacy_b" == "f" ]]; then
  legacy_winner='$argon2id$legacy-race-upgrade-a'
elif [[ "$legacy_a" == "f" && "$legacy_b" == "t" ]]; then
  legacy_winner='$argon2id$legacy-race-upgrade-b'
else
  echo "Expected one legacy-login CAS winner; got A=$legacy_a B=$legacy_b" >&2
  exit 1
fi

legacy_state="$(psql -X -qAt --set=ON_ERROR_STOP=1 -c "
select account.password_hash = '$legacy_winner'
  and count(session.*) = 1
  and bool_and(session.revoked_at is null)
from public.users as account
left join public.sessions as session on session.user_id = account.id
where account.id = '50000000-0000-4000-8000-000000000003'
group by account.password_hash;
")"
if [[ "$(printf '%s' "$legacy_state" | tr -d '\r\n[:space:]')" != "t" ]]; then
  echo "Legacy-login CAS winner did not define the committed state." >&2
  exit 1
fi
psql -X --set=ON_ERROR_STOP=1 -c "drop trigger delay_test_legacy_login on public.users; drop function public.delay_test_legacy_login();"
