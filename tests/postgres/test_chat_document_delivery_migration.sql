\set ON_ERROR_STOP on

create or replace function pg_temp.assert_true(
  condition boolean,
  failure_message text
)
returns void
language plpgsql
as $$
begin
  if condition is not true then
    raise exception 'PostgreSQL migration gate failed: %', failure_message;
  end if;
end;
$$;

select pg_temp.assert_true(
  has_column_privilege('service_role', 'public.chat_jobs', 'claim_token', 'SELECT'),
  'claim_token was not added to chat_jobs'
);

select pg_temp.assert_true(
  has_function_privilege('service_role', 'public.claim_chat_job_v2(uuid,uuid,uuid)', 'EXECUTE')
    and not has_function_privilege('anon', 'public.claim_chat_job_v2(uuid,uuid,uuid)', 'EXECUTE')
    and not has_function_privilege('authenticated', 'public.claim_chat_job_v2(uuid,uuid,uuid)', 'EXECUTE'),
  'claim_chat_job_v2 privileges are not service-role only'
);

select pg_temp.assert_true(
  has_function_privilege('service_role', 'public.release_chat_job_claim(uuid,uuid,uuid,text)', 'EXECUTE')
    and not has_function_privilege('anon', 'public.release_chat_job_claim(uuid,uuid,uuid,text)', 'EXECUTE')
    and not has_function_privilege('authenticated', 'public.release_chat_job_claim(uuid,uuid,uuid,text)', 'EXECUTE'),
  'release_chat_job_claim privileges are not service-role only'
);

select pg_temp.assert_true(
  has_function_privilege(
    'service_role',
    'public.consume_usage_event_v2(uuid,text,integer,jsonb)',
    'EXECUTE'
  )
    and not has_function_privilege(
      'anon',
      'public.consume_usage_event_v2(uuid,text,integer,jsonb)',
      'EXECUTE'
    )
    and not has_function_privilege(
      'authenticated',
      'public.consume_usage_event_v2(uuid,text,integer,jsonb)',
      'EXECUTE'
    ),
  'consume_usage_event_v2 privileges are not service-role only'
);

select pg_temp.assert_true(
  has_function_privilege(
    'service_role',
    'public.spend_credits_confirmed_v2(uuid,integer,text,text,text,integer,text,text,jsonb)',
    'EXECUTE'
  )
    and not has_function_privilege(
      'anon',
      'public.spend_credits_confirmed_v2(uuid,integer,text,text,text,integer,text,text,jsonb)',
      'EXECUTE'
    )
    and not has_function_privilege(
      'authenticated',
      'public.spend_credits_confirmed_v2(uuid,integer,text,text,text,integer,text,text,jsonb)',
      'EXECUTE'
    ),
  'spend_credits_confirmed_v2 privileges are not service-role only'
);

do $$
declare
  owner_id constant uuid := '10000000-0000-4000-8000-000000000001';
  first_event uuid;
  replay_event uuid;
  observed_used integer;
  was_allowed boolean;
  was_duplicate boolean;
begin
  select event_id, used, allowed, duplicate
  into first_event, observed_used, was_allowed, was_duplicate
  from public.consume_usage_event_v2(
    owner_id,
    'messages',
    1,
    '{"usageIdempotencyKey":"message-30000000-0000-4000-8000-000000000099","route":"chat"}'::jsonb
  );
  if not was_allowed or was_duplicate or observed_used <> 1 or first_event is null then
    raise exception 'first keyed usage event was not consumed';
  end if;

  select event_id, used, allowed, duplicate
  into replay_event, observed_used, was_allowed, was_duplicate
  from public.consume_usage_event_v2(
    owner_id,
    'messages',
    1,
    '{"usageIdempotencyKey":"message-30000000-0000-4000-8000-000000000099","route":"chat"}'::jsonb
  );
  if not was_allowed or not was_duplicate or replay_event <> first_event or observed_used <> 1 then
    raise exception 'keyed usage replay did not return the original allowance event';
  end if;
  if (select count(*) from public.usage_events where user_id = owner_id and event_type = 'messages') <> 1 then
    raise exception 'keyed usage replay inserted a duplicate allowance event';
  end if;
  if exists(
    select 1 from public.usage_events
    where id = first_event and metadata ? 'usageIdempotencyKey'
  ) then
    raise exception 'private usage idempotency key leaked into metadata';
  end if;
end;
$$;

do $$
declare
  owner_id constant uuid := '10000000-0000-4000-8000-000000000001';
  first_ledger uuid;
  replay_ledger uuid;
  retry_ledger uuid;
  observed_balance bigint;
  was_allowed boolean;
  was_duplicate boolean;
  exceeded boolean;
begin
  select ledger_id, balance, allowed, duplicate, limit_exceeded
  into first_ledger, observed_balance, was_allowed, was_duplicate, exceeded
  from public.spend_credits_confirmed_v2(
    owner_id, 10, 'feature_image_edit', 'quote-one', 'message:image-edit', 10,
    'feature:image_edit', 'message:image-edit', '{"route":"chat"}'::jsonb
  );
  if not was_allowed or was_duplicate or exceeded
     or first_ledger is null or observed_balance <> 90 then
    raise exception 'first keyed confirmed spend was not deducted';
  end if;

  select ledger_id, balance, allowed, duplicate, limit_exceeded
  into replay_ledger, observed_balance, was_allowed, was_duplicate, exceeded
  from public.spend_credits_confirmed_v2(
    owner_id, 10, 'feature_image_edit', 'quote-two', 'message:image-edit', 10,
    'feature:image_edit', 'message:image-edit', '{"route":"chat"}'::jsonb
  );
  if not was_allowed or not was_duplicate or exceeded
     or replay_ledger <> first_ledger or observed_balance <> 90 then
    raise exception 'fresh quote did not reconcile the active keyed spend';
  end if;

  update public.credit_accounts
  set balance = 100, lifetime_spent = 0
  where user_id = owner_id;
  insert into public.credit_ledger(
    user_id, delta, balance_after, reason, provider, related_ledger_id, metadata
  )
  values (
    owner_id, 10, 100, 'refund', 'internal', first_ledger,
    '{"reason":"fixture_failed"}'::jsonb
  );

  select ledger_id, balance, allowed, duplicate, limit_exceeded
  into replay_ledger, observed_balance, was_allowed, was_duplicate, exceeded
  from public.spend_credits_confirmed_v2(
    owner_id, 10, 'feature_image_edit', 'quote-one', 'message:image-edit', 10,
    'feature:image_edit', 'message:image-edit', '{"route":"chat"}'::jsonb
  );
  if was_allowed or was_duplicate or not exceeded or replay_ledger is not null then
    raise exception 'refunded approval became reusable';
  end if;

  select ledger_id, balance, allowed, duplicate, limit_exceeded
  into retry_ledger, observed_balance, was_allowed, was_duplicate, exceeded
  from public.spend_credits_confirmed_v2(
    owner_id, 10, 'feature_image_edit', 'quote-three', 'message:image-edit', 10,
    'feature:image_edit', 'message:image-edit', '{"route":"chat"}'::jsonb
  );
  if not was_allowed or was_duplicate or exceeded
     or retry_ledger is null or retry_ledger = first_ledger
     or observed_balance <> 90 then
    raise exception 'new confirmation could not retry a refunded keyed spend';
  end if;
  if (
    select count(*)
    from public.credit_ledger
    where user_id = owner_id and provider = 'feature-spend' and delta < 0
  ) <> 2 then
    raise exception 'keyed paid replay created an unexpected spend count';
  end if;
end;
$$;

select pg_temp.assert_true(
  has_function_privilege(
    'service_role',
    'public.begin_chat_manuscript_workspace(uuid,uuid,uuid,uuid,uuid,integer,text,text,text,text,text,text,integer,integer,text,jsonb,integer,integer,text)',
    'EXECUTE'
  )
    and not has_function_privilege(
      'anon',
      'public.begin_chat_manuscript_workspace(uuid,uuid,uuid,uuid,uuid,integer,text,text,text,text,text,text,integer,integer,text,jsonb,integer,integer,text)',
      'EXECUTE'
    )
    and not has_function_privilege(
      'authenticated',
      'public.begin_chat_manuscript_workspace(uuid,uuid,uuid,uuid,uuid,integer,text,text,text,text,text,text,integer,integer,text,jsonb,integer,integer,text)',
      'EXECUTE'
    ),
  'begin_chat_manuscript_workspace privileges are not service-role only'
);

select pg_temp.assert_true(
  has_function_privilege('service_role', 'public.retire_generated_document_versions(uuid,uuid,uuid)', 'EXECUTE')
    and not has_function_privilege('anon', 'public.retire_generated_document_versions(uuid,uuid,uuid)', 'EXECUTE')
    and not has_function_privilege('authenticated', 'public.retire_generated_document_versions(uuid,uuid,uuid)', 'EXECUTE'),
  'retire_generated_document_versions privileges are not service-role only'
);

do $$
declare
  owner_id constant uuid := '10000000-0000-4000-8000-000000000001';
  fixture_chat_id constant uuid := '20000000-0000-4000-8000-000000000001';
  fixture_message_id constant uuid := '30000000-0000-4000-8000-000000000001';
  state text;
  response jsonb;
  first_token uuid;
  next_token uuid;
  released boolean;
begin
  select job_state, response_data, claim_token
    into state, response, first_token
  from public.claim_chat_job_v2(owner_id, fixture_chat_id, fixture_message_id);
  if state <> 'claimed' or first_token is null then
    raise exception 'new v2 claim did not return an ownership token';
  end if;

  select job_state, response_data, claim_token
    into state, response, next_token
  from public.claim_chat_job_v2(owner_id, fixture_chat_id, fixture_message_id);
  if state <> 'busy' or next_token is not null then
    raise exception 'live eight-minute lease was not busy';
  end if;

  update public.chat_jobs
  set updated_at = now() - interval '8 minutes 1 second'
  where chat_jobs.user_id = owner_id and chat_jobs.message_id = fixture_message_id;

  select job_state, response_data, claim_token
    into state, response, next_token
  from public.claim_chat_job_v2(owner_id, fixture_chat_id, fixture_message_id);
  if state <> 'claimed' or next_token is null or next_token = first_token then
    raise exception 'stale takeover did not rotate ownership token';
  end if;

  select public.release_chat_job_claim(owner_id, fixture_message_id, first_token, 'STALE') into released;
  if released then
    raise exception 'stale worker released a newer claim';
  end if;
  select public.release_chat_job_claim(owner_id, fixture_message_id, next_token, 'EXPECTED') into released;
  if not released then
    raise exception 'current worker could not release its claim';
  end if;

  select job_state, response_data, claim_token
    into state, response, first_token
  from public.claim_chat_job_v2(owner_id, fixture_chat_id, fixture_message_id);
  update public.chat_jobs
  set updated_at = now() - interval '8 minutes 1 second'
  where chat_jobs.user_id = owner_id and chat_jobs.message_id = fixture_message_id;
  select job_state into state
  from public.claim_chat_job(owner_id, fixture_chat_id, fixture_message_id);
  if state <> 'claimed' then
    raise exception 'legacy rolling caller did not reclaim stale work';
  end if;
  if (select claim_token from public.chat_jobs where chat_jobs.user_id = owner_id and chat_jobs.message_id = fixture_message_id) is not null then
    raise exception 'legacy reclaim inherited a v2 ownership token';
  end if;
  select public.release_chat_job_claim(owner_id, fixture_message_id, first_token, 'STALE') into released;
  if released then
    raise exception 'pre-rollback v2 worker released a legacy-owned claim';
  end if;

  update public.chat_jobs
  set status = 'completed', response_data = '{"response":"durable"}'::jsonb
  where chat_jobs.user_id = owner_id and chat_jobs.message_id = fixture_message_id;
  select job_state, response_data, claim_token
    into state, response, next_token
  from public.claim_chat_job_v2(owner_id, fixture_chat_id, fixture_message_id);
  if state <> 'completed' or response <> '{"response":"durable"}'::jsonb then
    raise exception 'completed durable response was not reconciled';
  end if;
end;
$$;

do $$
declare
  owner_id constant uuid := '10000000-0000-4000-8000-000000000001';
  fixture_chat_id constant uuid := '20000000-0000-4000-8000-000000000011';
  fixture_message_id constant uuid := '30000000-0000-4000-8000-000000000011';
  claim uuid;
  first_project jsonb;
  first_manuscript jsonb;
  first_run jsonb;
  next_project jsonb;
  next_manuscript jsonb;
  next_run jsonb;
  was_created boolean;
  was_reconciled boolean;
begin
  select claim_token into claim
  from public.claim_chat_job_v2(owner_id, fixture_chat_id, fixture_message_id);

  select project_row, manuscript_row, run_row, project_created, reconciled
  into first_project, first_manuscript, first_run, was_created, was_reconciled
  from public.begin_chat_manuscript_workspace(
    owner_id, fixture_chat_id, fixture_message_id, claim, null, 3,
    'The Glass Orchard', 'A durable novel workspace', 'Keep the canon stable',
    'The Glass Orchard', 'Founder', 'Write a 70000 word novel in 24 chapters.',
    70000, 24, 'epub', '{"eventId":"blueprint-1"}'::jsonb,
    64, 8, 'action-1'
  );
  if not was_created or was_reconciled then
    raise exception 'first manuscript handoff did not create one new workspace';
  end if;

  select project_row, manuscript_row, run_row, project_created, reconciled
  into next_project, next_manuscript, next_run, was_created, was_reconciled
  from public.begin_chat_manuscript_workspace(
    owner_id, fixture_chat_id, fixture_message_id, claim, null, 3,
    'Changed replay title', '', '', 'Changed replay title', 'Founder',
    'A replay must reconcile rather than duplicate.', 80000, 28, 'docx',
    '{"eventId":"blueprint-replay"}'::jsonb, 0, 0, 'action-replay'
  );
  if was_created or not was_reconciled then
    raise exception 'replayed manuscript handoff was not reconciled';
  end if;
  if first_project->>'id' <> next_project->>'id'
     or first_manuscript->>'id' <> next_manuscript->>'id'
     or first_run->>'id' <> next_run->>'id' then
    raise exception 'replayed manuscript handoff changed durable identities';
  end if;
  if (select count(*) from public.projects where user_id = owner_id) <> 1
     or (select count(*) from public.manuscripts where user_id = owner_id) <> 1
     or (select count(*) from public.manuscript_runs where user_id = owner_id) <> 1 then
    raise exception 'replayed manuscript handoff created duplicate rows';
  end if;
end;
$$;

create or replace function pg_temp.reject_atomic_manuscript_fixture()
returns trigger
language plpgsql
as $$
begin
  if new.source_message_id = '30000000-0000-4000-8000-000000000012'::uuid then
    raise exception 'intentional atomic rollback fixture';
  end if;
  return new;
end;
$$;

create trigger reject_atomic_manuscript_fixture
before insert on public.manuscript_runs
for each row execute function pg_temp.reject_atomic_manuscript_fixture();

do $$
declare
  owner_id constant uuid := '10000000-0000-4000-8000-000000000001';
  fixture_chat_id constant uuid := '20000000-0000-4000-8000-000000000012';
  fixture_message_id constant uuid := '30000000-0000-4000-8000-000000000012';
  claim uuid;
begin
  select claim_token into claim
  from public.claim_chat_job_v2(owner_id, fixture_chat_id, fixture_message_id);
  begin
    perform * from public.begin_chat_manuscript_workspace(
      owner_id, fixture_chat_id, fixture_message_id, claim, null, 3,
      'Atomic rollback proof', '', '', 'Atomic rollback proof', 'Founder',
      'This insert is intentionally rejected at the final run step.',
      50000, 16, 'pdf', '{}'::jsonb, 0, 0, 'atomic-action'
    );
    raise exception 'intentional run rejection did not occur';
  exception
    when others then
      if sqlerrm = 'intentional run rejection did not occur' then
        raise;
      end if;
  end;

  if exists(select 1 from public.projects where name = 'Atomic rollback proof')
     or exists(select 1 from public.manuscripts where title = 'Atomic rollback proof')
     or exists(select 1 from public.project_chats where chat_id = fixture_chat_id)
     or exists(select 1 from public.manuscript_runs where source_message_id = fixture_message_id) then
    raise exception 'failed manuscript handoff left partial durable rows';
  end if;
end;
$$;

drop trigger reject_atomic_manuscript_fixture on public.manuscript_runs;

do $$
declare
  owner_id constant uuid := '10000000-0000-4000-8000-000000000001';
  other_id constant uuid := '10000000-0000-4000-8000-000000000002';
  logical_id constant uuid := '40000000-0000-4000-8000-000000000001';
  old_id constant uuid := '41000000-0000-4000-8000-000000000001';
  keep_id constant uuid := '42000000-0000-4000-8000-000000000001';
  other_file_id constant uuid := '43000000-0000-4000-8000-000000000001';
  retired integer;
begin
  insert into public.user_files(
    id, user_id, storage_path, file_name, mime_type, kind, status, metadata
  ) values
    (old_id, owner_id, owner_id::text || '/old.docx', 'old.docx', 'application/test', 'generated_document', 'ready', jsonb_build_object('_logicalArtifactId', logical_id::text)),
    (keep_id, owner_id, owner_id::text || '/new.docx', 'new.docx', 'application/test', 'generated_document', 'ready', jsonb_build_object('_logicalArtifactId', logical_id::text)),
    (other_file_id, other_id, other_id::text || '/other.docx', 'other.docx', 'application/test', 'generated_document', 'ready', jsonb_build_object('_logicalArtifactId', logical_id::text));

  select public.retire_generated_document_versions(owner_id, logical_id, keep_id)
    into retired;
  if retired <> 1 then
    raise exception 'expected one superseded owner version, got %', retired;
  end if;
  if (select deleted_at is null from public.user_files where id = old_id) then
    raise exception 'old owner version remained active';
  end if;
  if not (select deleted_at is null from public.user_files where id = keep_id) then
    raise exception 'kept owner version was retired';
  end if;
  if not (select deleted_at is null from public.user_files where id = other_file_id) then
    raise exception 'another owner version was modified';
  end if;
end;
$$;
