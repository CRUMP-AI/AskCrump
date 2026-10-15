/** Real PostgreSQL SQL semantics in fresh in-memory PGlite, not concurrent sessions.
 * Uses actual deployed wallet/allowance RPC bodies and the new migration. Never
 * reads DATABASE_URL, a linked Supabase project, credentials, or customer rows.
 * PGLITE_MODULE may point to an already installed package's dist/index.js.
 */
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { fileURLToPath, pathToFileURL } from 'node:url';
import path from 'node:path';
import { randomUUID } from 'node:crypto';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const read = name => readFile(path.join(root, 'migrations', name), 'utf8');
const require = createRequire(import.meta.url);
let modulePath = process.env.PGLITE_MODULE;
if (!modulePath) {
  try { modulePath = require.resolve('@electric-sql/pglite'); }
  catch { throw new Error('Set PGLITE_MODULE to an existing PGlite dist/index.js; no dependency will be installed.'); }
}
const { PGlite } = await import(pathToFileURL(path.resolve(modulePath)).href);
const db = new PGlite();
const user = randomUUID(), user2 = randomUUID(), project = randomUUID();
const basePolicy = { model: 'exact-approved-model', input_rate: 1_000_000, output_rate: 1_000_000,
  max_input_bytes: 100_000, max_output_tokens: 6000, call_limit: 20_000, run_limit: 40_000,
  account_daily_limit: 60_000, global_daily_limit: 100_000 };
let groups = 0;
const one = async (sql, args = []) => (await db.query(sql, args)).rows[0];
async function rpc(name, args) {
  const placeholders = args.map((_, i) => `$${i + 1}`).join(',');
  return (await one(`select public.${name}(${placeholders}) as result`, args)).result;
}
async function group(name, run) {
  await db.exec('begin');
  try { await run(); groups++; console.log(`PASS ${name}`); }
  finally { await db.exec('rollback'); }
}
async function task({ owner = user, policy = basePolicy, included = 3, credits = 12, confirmed = 12,
                      bypass = null, dispatch = true } = {}) {
  const id = randomUUID(), lease = randomUUID();
  await db.query(`insert into public.code_tasks(id,user_id,project_id,objective,source_repo_url)
    values($1,$2,$3,'A bounded offline SQL fixture','https://github.com/example/fixture')`, [id, owner, project]);
  const t = { id, user_id: owner, lease_token: lease, policy };
  if (dispatch) {
    t.dispatch = await dispatchTask(t, { included, credits, confirmed, bypass });
  }
  return t;
}
async function dispatchTask(t, { included = 3, credits = 12, confirmed = 12, bypass = null, token = randomUUID() } = {}) {
  return rpc('reserve_and_dispatch_code_task', [t.id, t.user_id, token, included, credits, confirmed,
    randomUUID(), bypass, t.policy]);
}
async function running(t) {
  await db.query(`update public.code_tasks set status='running',lease_token=$2,
    lease_expires_at=clock_timestamp()+interval '5 minutes' where id=$1`, [t.id, t.lease_token]);
  return t;
}
async function reserve(t, { key = 'turn:0', digest = 'a'.repeat(64), input = 5000, output = 1000,
                          amount = input + output, policy = t.policy } = {}) {
  return rpc('reserve_code_provider_call', [t.id, t.user_id, t.lease_token, key, digest, amount, input, output, policy]);
}
const begin = (t, r) => rpc('begin_code_provider_call', [t.id, t.user_id, t.lease_token, r.id]);
const settle = (t, r, amount, uncertain = false) => rpc('settle_code_provider_call', [t.id, t.user_id, t.lease_token, r.id, amount, uncertain]);
const release = (t, r) => rpc('release_code_provider_call', [t.id, t.user_id, t.lease_token, r.id]);
const refund = t => rpc('refund_code_task_if_unstarted', [t.id, t.user_id]);
const readTask = t => one('select * from public.code_tasks where id=$1', [t.id]);
const globalDay = (offset = 0) => one(`select held_micros::text as held,strictest_cap_micros::text as cap
  from public.code_provider_global_daily where budget_day=(clock_timestamp() at time zone 'UTC')::date+$1::integer`, [offset]);
const accountDay = owner => one(`select held_micros::text as held,strictest_cap_micros::text as cap
  from public.code_provider_account_daily where user_id=$1 and budget_day=(clock_timestamp() at time zone 'UTC')::date`, [owner]);
async function terminal(t) { await db.query("update public.code_tasks set status='cancelled',payment_source='refund_pending',lease_token=null where id=$1", [t.id]); }

try {
  await db.exec(`create role anon; create role authenticated; create role service_role bypassrls;
    create table public.users(id uuid primary key,deleted_at timestamptz);
    create table public.projects(id uuid primary key,user_id uuid);
    create table public.usage_events(id uuid primary key default gen_random_uuid(),user_id uuid not null references public.users,
      event_type text not null,metadata jsonb not null default '{}',created_at timestamptz not null default now());`);
  await db.exec(await read('005_credit_wallet.sql'));
  // Apply the exact relevant v2 functions, not handwritten substitutes. The rest
  // of that broad migration needs unrelated chat/manuscript schemas.
  const v2 = await read('20260924213808_align_chat_job_lease_with_ai_timeout.sql');
  await db.exec(`alter table public.usage_events add column idempotency_key text;
    create unique index fixture_usage_key on public.usage_events(user_id,event_type,idempotency_key) where idempotency_key is not null;`);
  await db.exec(v2.slice(v2.indexOf('create or replace function public.consume_usage_event_v2('),
                       v2.indexOf('create or replace function public.claim_chat_job(')));
  await db.exec(await read('20260827145025_crump_code_foundation.sql'));
  await db.exec(await read('20260830093000_crump_code_durable_worker.sql'));
  await db.exec(`create table public.user_chats(user_id uuid references public.users);
    create table public.user_settings(user_id uuid references public.users);
    create table public.sessions(user_id uuid references public.users);`);
  await db.exec(await read('20260924210000_durable_account_storage_deletion.sql'));
  await db.exec(await read('20261015230059_atomic_code_dispatch_provider_budget.sql'));
  await db.query('insert into public.users(id) values($1),($2)', [user, user2]);
  await db.query('insert into public.projects(id,user_id) values($1,$2)', [project, user]);
  await db.query('insert into public.credit_accounts(user_id,balance) values($1,100),($2,100)', [user, user2]);

  await group('atomic included dispatch, cross-request replay and immutable canonical receipt', async () => {
    const t = await task();
    assert.equal(t.dispatch.outcome, 'dispatched');
    const first = t.dispatch.task;
    assert.equal(first.status, 'provisioning');
    assert.equal(first.usage_receipt.paymentSource, 'included');
    assert.ok(first.usage_receipt.eventId);
    const replay = await dispatchTask(t, { included: 0, credits: 999, confirmed: 0 });
    assert.equal(replay.outcome, 'replay');
    assert.deepEqual(replay.task, first);
    assert.equal((await one('select count(*)::int as n from public.usage_events')).n, 1);
    assert.equal((await one("select count(*)::int as n from public.code_task_events where event_type='task.claimed'")).n, 1);
    const wrongOwner = { ...t, user_id: user2 };
    assert.equal((await dispatchTask(wrongOwner)).code, 'CODE_TASK_NOT_FOUND');
  });

  await group('paid dispatch deducts exactly once; pre-provider cancellation refunds exactly once', async () => {
    const t = await task({ included: 0 });
    assert.equal(t.dispatch.task.credits_spent, 12);
    assert.match(t.dispatch.task.usage_receipt.eventId, /^credit:/);
    await dispatchTask(t);
    assert.equal((await one('select balance::int from public.credit_accounts where user_id=$1', [user])).balance, 88);
    await terminal(t);
    const first = await refund(t), second = await refund(t);
    assert.equal(first.outcome, 'refunded');
    assert.equal(second.outcome, 'no_receipt');
    assert.equal(second.task.payment_source, 'refunded');
    assert.equal((await one('select balance::int from public.credit_accounts where user_id=$1', [user])).balance, 100);
    assert.equal((await one("select count(*)::int as n from public.credit_ledger where reason='refund'")).n, 1);
  });

  await group('stale free allowance never silently spends unconfirmed credits', async () => {
    const first = await task({ included: 1, confirmed: 0 });
    assert.equal(first.dispatch.outcome, 'dispatched');
    const raced = await task({ included: 1, confirmed: 0 });
    assert.equal(raced.dispatch.code, 'CREDIT_CONFIRMATION_REQUIRED');
    assert.equal((await readTask(raced)).dispatch_token, null);
    assert.equal((await one('select count(*)::int as n from public.credit_ledger')).n, 0);
    assert.equal((await dispatchTask(raced, { included: 1, confirmed: 12 })).outcome, 'dispatched');
    assert.equal((await one('select balance::int from public.credit_accounts where user_id=$1', [user])).balance, 88);
  });

  await group('transaction failure after debit rolls back both charge and dispatch', async () => {
    const t = await task({ dispatch: false });
    await db.exec(`create function public.fixture_reject_event() returns trigger language plpgsql as $$
      begin raise exception 'intentional event persistence failure'; end $$;
      create trigger fixture_reject_event before insert on public.code_task_events for each row execute function public.fixture_reject_event();`);
    await db.exec('savepoint failed_dispatch');
    await assert.rejects(dispatchTask(t, { included: 0 }), /intentional event persistence failure/);
    await db.exec('rollback to savepoint failed_dispatch');
    assert.equal((await readTask(t)).dispatch_token, null);
    assert.equal((await one('select balance::int from public.credit_accounts where user_id=$1', [user])).balance, 100);
    assert.equal((await one('select count(*)::int as n from public.credit_ledger')).n, 0);
    await db.exec('drop trigger fixture_reject_event on public.code_task_events');
    assert.equal((await dispatchTask(t, { included: 0 })).outcome, 'dispatched');
  });

  await group('input price recomputed in SQL; exact pinned policy and digest required', async () => {
    const t = await running(await task());
    assert.equal((await reserve(t, { amount: 1 })).code, 'CODE_PROVIDER_BUDGET_EXHAUSTED');
    assert.equal((await reserve(t, { policy: { ...basePolicy, run_limit: 50_000 } })).code, 'CODE_BUDGET_POLICY_CONFLICT');
    const r = await reserve(t);
    assert.equal(r.outcome, 'reserved');
    assert.equal((await reserve(t)).outcome, 'reserved_replay');
    assert.equal((await reserve(t, { digest: 'b'.repeat(64) })).code, 'CODE_PROVIDER_CALL_CONFLICT');
    assert.equal((await reserve(t, { input: 1 })).code, 'CODE_BUDGET_POLICY_CONFLICT');
    assert.equal((await reserve({ ...t, user_id: user2 })).code, 'CODE_PROVIDER_LEASE_CONFLICT');
    assert.equal((await one('select count(*)::int as n from public.code_provider_call_reservations')).n, 1);
  });

  await group('begin monotonic; uncertain outcomes retain hold and forbid call replay or new calls', async () => {
    const t = await running(await task({ included: 0 }));
    const r = (await reserve(t)).reservation;
    assert.equal((await begin(t, r)).outcome, 'started');
    assert.equal((await begin(t, r)).outcome, 'already_started');
    assert.equal((await release(t, r)).code, 'CODE_PROVIDER_OUTCOME_UNCERTAIN');
    assert.equal((await reserve(t, { key: 'turn:1' })).code, 'CODE_PROVIDER_OUTCOME_UNCERTAIN');
    assert.equal((await settle(t, r, null, true)).outcome, 'uncertain');
    assert.equal((await settle(t, r, null, true)).outcome, 'settled_replay');
    assert.equal((await settle(t, r, 1)).outcome, 'uncertain');
    assert.equal((await settle(t, r, 1)).outcome, 'settled_replay');
    assert.equal((await one('select status from public.code_provider_call_reservations where id=$1', [r.id])).status, 'uncertain');
    const started = await readTask(t);
    assert.ok(started.provider_started_at);
    await db.query('update public.code_tasks set provider_started_at=null,provider_execution_lease_token=null where id=$1', [t.id]);
    assert.equal((await readTask(t)).provider_execution_lease_token, t.lease_token);
    await terminal(t);
    const held = await refund(t);
    assert.equal(held.outcome, 'provider_started');
    assert.equal(held.task.payment_source, 'credits');
    assert.equal((await one('select balance::int from public.credit_accounts where user_id=$1', [user])).balance, 88);
    assert.equal((await one("select status from public.code_provider_call_reservations where id=$1", [r.id])).status, 'uncertain');
  });

  await group('cancellation before begin releases unused holds and restores included allowance', async () => {
    const t = await running(await task());
    const r = (await reserve(t)).reservation;
    await terminal(t);
    assert.equal((await begin(t, r)).code, 'CODE_PROVIDER_LEASE_CONFLICT');
    assert.equal((await refund(t)).outcome, 'refunded');
    assert.equal((await one('select count(*)::int as n from public.usage_events')).n, 0);
    assert.equal((await one('select status from public.code_provider_call_reservations where id=$1', [r.id])).status, 'released');
    assert.equal((await readTask(t)).provider_started_at, null);
  });

  await group('settlement shrinks held costs, records overruns, and allows original owner after terminal expiry', async () => {
    const t = await running(await task());
    let r = (await reserve(t)).reservation;
    await begin(t, r);
    assert.equal((await settle(t, r, 100)).outcome, 'settled');
    assert.equal((await settle(t, r, 100)).outcome, 'settled_replay');
    r = (await reserve(t, { key: 'turn:1' })).reservation;
    await begin(t, r);
    await terminal(t);
    await db.query("update public.code_tasks set expires_at=clock_timestamp()-interval '1 second' where id=$1", [t.id]);
    assert.equal((await settle(t, r, 10_000)).outcome, 'uncertain');
    assert.equal((await one('select actual_micros::int as n from public.code_provider_call_reservations where id=$1', [r.id])).n, 10_000);
    assert.equal((await settle({ ...t, lease_token: randomUUID() }, r, 10_000)).code, 'CODE_PROVIDER_LEASE_CONFLICT');
  });

  await group('run, account, global caps and stricter same-day policy are independently enforced', async () => {
    // A 6k call consumes most of each 10k run. Multiple accounts share 30k global.
    const p = { ...basePolicy, call_limit: 10_000, run_limit: 10_000,
      account_daily_limit: 20_000, global_daily_limit: 30_000 };
    const a = await running(await task({ policy: p }));
    let r = (await reserve(a)).reservation; await begin(a, r); await settle(a, r, 6000);
    assert.equal((await reserve(a, { key: 'turn:1' })).code, 'CODE_PROVIDER_BUDGET_EXHAUSTED');
    for (let i = 0; i < 2; i++) {
      const t = await running(await task({ policy: p }));
      r = (await reserve(t)).reservation; await begin(t, r); await settle(t, r, 6000);
    }
    const accountBlocked = await running(await task({ policy: p }));
    assert.equal((await reserve(accountBlocked)).code, 'CODE_PROVIDER_BUDGET_EXHAUSTED');
    const b = await running(await task({ owner: user2, policy: p }));
    r = (await reserve(b)).reservation; await begin(b, r); await settle(b, r, 6000);
    const c = await running(await task({ owner: user2, policy: p }));
    r = (await reserve(c)).reservation; await begin(c, r); await settle(c, r, 6000);
    const globalBlocked = await running(await task({ owner: user2, policy: basePolicy }));
    assert.equal((await reserve(globalBlocked)).code, 'CODE_PROVIDER_BUDGET_EXHAUSTED');
  });

  await group('expired unused lease can rebind; begun lease cannot be reclaimed or redispatched', async () => {
    const unused = await running(await task());
    const first = (await reserve(unused)).reservation;
    await db.query("update public.code_tasks set lease_expires_at=clock_timestamp()-interval '1 second' where id=$1", [unused.id]);
    assert.equal((await begin(unused, first)).code, 'CODE_PROVIDER_LEASE_CONFLICT');
    const lease2 = randomUUID();
    const claimed = await db.query('select * from public.claim_code_task(120,$1)', [lease2]);
    assert.equal(claimed.rows[0].id, unused.id);
    unused.lease_token = lease2; await running(unused);
    const rebound = await reserve(unused);
    assert.equal(rebound.outcome, 'reserved_replay');
    assert.equal(rebound.reservation.lease_token, lease2);
    await begin(unused, rebound.reservation);
    await db.query("update public.code_tasks set lease_expires_at=clock_timestamp()-interval '1 second' where id=$1", [unused.id]);
    assert.equal((await db.query('select * from public.claim_code_task(120,$1)', [randomUUID()])).rows.length, 0);
    unused.lease_token = randomUUID(); await running(unused);
    assert.equal((await reserve(unused, { key: 'turn:1' })).code, 'CODE_PROVIDER_LEASE_CONFLICT');
  });

  await group('UTC-day rollover refuses old hold; exact release is pre-dispatch only', async () => {
    const t = await running(await task());
    // A prior-day fixture represents a hold made before UTC rollover. Its
    // immutable accounting date cannot be moved to free today's capacity.
    const r = await one(`insert into public.code_provider_call_reservations(id,task_id,user_id,call_key,request_sha256,
      lease_token,policy,reserved_micros,input_ceiling,output_ceiling,budget_day,expires_at)
      values($1,$2,$3,'turn:0',$4,$5,$6,6000,5000,1000,(clock_timestamp() at time zone 'UTC')::date-1,
      clock_timestamp()+interval '5 minutes') returning *`, [randomUUID(),t.id,t.user_id,'a'.repeat(64),t.lease_token,t.policy]);
    assert.deepEqual(await globalDay(-1), { held: '6000', cap: '100000' });
    assert.equal(await globalDay(), undefined);
    assert.equal((await reserve(t)).code, 'CODE_PROVIDER_DAY_CONFLICT');
    assert.equal((await begin(t, r)).code, 'CODE_PROVIDER_LEASE_CONFLICT');
    assert.equal((await release(t, r)).outcome, 'released');
    assert.equal((await release(t, r)).outcome, 'released');
    assert.equal((await begin(t, r)).code, 'CODE_PROVIDER_LEASE_CONFLICT');
    assert.deepEqual(await globalDay(-1), { held: '0', cap: '100000' });
    assert.equal((await reserve(t, { key: 'turn:1' })).outcome, 'reserved');
    assert.deepEqual(await globalDay(), { held: '6000', cap: '100000' });
    const late = await one(`insert into public.code_provider_call_reservations(id,task_id,user_id,call_key,request_sha256,
      lease_token,policy,reserved_micros,input_ceiling,output_ceiling,status,budget_day,expires_at,started_at)
      values($1,$2,$3,'prior-day-started',$4,$5,$6,6000,5000,1000,'started',(clock_timestamp() at time zone 'UTC')::date-1,
      clock_timestamp()-interval '1 minute',clock_timestamp()-interval '1 day') returning *`,
      [randomUUID(),t.id,t.user_id,'b'.repeat(64),t.lease_token,t.policy]);
    assert.equal((await settle(t, late, 9000)).outcome, 'uncertain');
    assert.deepEqual(await globalDay(-1), { held: '9000', cap: '100000' });
    assert.deepEqual(await globalDay(), { held: '6000', cap: '100000' });
    await db.exec('savepoint immutable_day');
    await assert.rejects(db.query('update public.code_provider_call_reservations set budget_day=budget_day+1 where id=$1', [r.id]), /admission identity is immutable/);
    await db.exec('rollback to savepoint immutable_day');
  });

  await group('expired started lease retires atomically while live extension wins and costs remain held', async () => {
    const t = await running(await task({ included: 0 }));
    const r = (await reserve(t)).reservation;
    await begin(t, r);
    const reconcile = () => rpc('reconcile_code_provider_lease', [t.id, t.user_id]);
    assert.equal((await reconcile()).outcome, 'unchanged');
    await db.query("update public.code_tasks set lease_expires_at=clock_timestamp()-interval '1 second' where id=$1", [t.id]);
    // A reconciler selected an old row, but the active worker extended first.
    await db.query("update public.code_tasks set lease_expires_at=clock_timestamp()+interval '1 minute' where id=$1", [t.id]);
    assert.equal((await reconcile()).outcome, 'unchanged');
    await db.query("update public.code_tasks set lease_expires_at=clock_timestamp()-interval '1 second' where id=$1", [t.id]);
    const retired = await reconcile();
    assert.equal(retired.outcome, 'failed_uncertain');
    assert.equal(retired.task.failure_code, 'CODE_PROVIDER_OUTCOME_UNCERTAIN');
    assert.equal(retired.task.lease_token, null);
    assert.equal(retired.task.payment_source, 'credits');
    assert.equal((await reconcile()).outcome, 'unchanged');
    assert.equal((await one("select count(*)::int as n from public.code_task_events where event_type='task.failed'")).n, 1);
    assert.equal((await one('select status from public.code_provider_call_reservations where id=$1', [r.id])).status, 'uncertain');
    // A late provider reply cannot undo uncertainty; an overrun must still
    // increase the ledger's conservative known cost after retirement.
    assert.equal((await settle(t, r, 9000)).outcome, 'uncertain');
    assert.equal((await one('select actual_micros::int as n from public.code_provider_call_reservations where id=$1', [r.id])).n, 9000);
    assert.equal((await settle(t, r, 1)).code, 'CODE_PROVIDER_CALL_CONFLICT');
    assert.equal((await refund(t)).outcome, 'provider_started');
    assert.equal((await one('select balance::int from public.credit_accounts where user_id=$1', [user])).balance, 88);
  });

  await group('daily aggregates apply exact reserve, release, settlement and uncertain-overrun deltas', async () => {
    const unused = await running(await task());
    const first = (await reserve(unused)).reservation;
    assert.deepEqual(await globalDay(), { held: '6000', cap: '100000' });
    await reserve(unused);
    assert.equal((await globalDay()).held, '6000');
    await release(unused, first);
    assert.equal((await globalDay()).held, '0');
    await release(unused, first);
    assert.equal((await globalDay()).held, '0');
    const t = await running(await task());
    let r = (await reserve(t)).reservation;
    await begin(t, r); await settle(t, r, 1000);
    assert.equal((await globalDay()).held, '1000');
    await settle(t, r, 1000);
    assert.equal((await globalDay()).held, '1000');
    r = (await reserve(t, { key: 'turn:1' })).reservation;
    assert.equal((await globalDay()).held, '7000');
    await begin(t, r); await settle(t, r, null, true);
    assert.equal((await globalDay()).held, '7000');
    await settle(t, r, 9000);
    assert.equal((await globalDay()).held, '10000');
    await settle(t, r, 9000);
    assert.equal((await settle(t, r, 1)).code, 'CODE_PROVIDER_CALL_CONFLICT');
    assert.equal((await globalDay()).held, '10000');
    assert.deepEqual(await accountDay(user), { held: '10000', cap: '60000' });
  });

  await group('account deletion cannot free global spent or uncertain holds or loosen strictest daily cap', async () => {
    const p = { ...basePolicy, call_limit: 6000, run_limit: 12000, account_daily_limit: 18000, global_daily_limit: 18000 };
    const a = await running(await task({ policy: p, included: -1, bypass: 'internal' }));
    let r = (await reserve(a)).reservation;
    await begin(a, r); await settle(a, r, 6000);
    const b = await running(await task({ policy: p, included: -1, bypass: 'internal' }));
    r = (await reserve(b)).reservation;
    await begin(b, r); await settle(b, r, null, true);
    const c = await running(await task({ policy: p, included: -1, bypass: 'internal' }));
    assert.equal((await reserve(c)).outcome, 'reserved');
    assert.deepEqual(await globalDay(), { held: '18000', cap: '18000' });
    await db.query("insert into public.usage_events(user_id,event_type) values($1,'fixture')", [user]);
    for (const table of ['user_chats','user_settings','sessions']) {
      await db.query(`insert into public.${table}(user_id) values($1)`, [user]);
    }
    await db.exec('set local role service_role');
    await rpc('delete_user_account', [user,'crump-files']);
    await db.exec('reset role');
    assert.equal((await one('select count(*)::int as n from public.code_provider_call_reservations')).n, 0);
    assert.equal((await one('select count(*)::int as n from public.code_provider_account_daily')).n, 0);
    assert.deepEqual(await globalDay(), { held: '18000', cap: '18000' });
    const cleanup = await one('select id,bucket,owner_prefix,status from public.account_storage_deletion_jobs where user_id=$1', [user]);
    assert.equal(cleanup.owner_prefix, `${user}/`); assert.equal(cleanup.status, 'pending');
    await rpc('delete_user_account', [user]);
    assert.deepEqual(await one('select id,bucket,owner_prefix,status from public.account_storage_deletion_jobs where user_id=$1', [user]), cleanup);
    for (const table of ['usage_events','user_chats','user_settings','sessions']) {
      assert.equal((await one(`select count(*)::int as n from public.${table} where user_id=$1`, [user])).n, 0);
    }
    const neighbor = await running(await task({ owner: user2, policy: basePolicy }));
    assert.equal((await reserve(neighbor)).code, 'CODE_PROVIDER_BUDGET_EXHAUSTED');
    const columns = (await db.query(`select column_name from information_schema.columns
      where table_schema='public' and table_name='code_provider_global_daily' order by ordinal_position`)).rows.map(row => row.column_name);
    assert.deepEqual(columns, ['budget_day','held_micros','strictest_cap_micros','updated_at']);
  });

  await group('task deletion preserves account and global daily accounting and their cap minima', async () => {
    const p = { ...basePolicy, call_limit: 6000, run_limit: 6000, account_daily_limit: 6000, global_daily_limit: 12000 };
    const t = await running(await task({ policy: p, included: -1, bypass: 'internal' }));
    const r = (await reserve(t)).reservation;
    await begin(t, r); await settle(t, r, 6000);
    await db.query('delete from public.code_tasks where id=$1', [t.id]);
    assert.equal((await one('select count(*)::int as n from public.code_provider_call_reservations')).n, 0);
    assert.deepEqual(await accountDay(user), { held: '6000', cap: '6000' });
    assert.deepEqual(await globalDay(), { held: '6000', cap: '12000' });
    const sameAccount = await running(await task({ policy: basePolicy }));
    assert.equal((await reserve(sameAccount)).code, 'CODE_PROVIDER_BUDGET_EXHAUSTED');
    const neighbor = await running(await task({ owner: user2, policy: basePolicy }));
    assert.equal((await reserve(neighbor)).outcome, 'reserved');
    assert.deepEqual(await globalDay(), { held: '12000', cap: '12000' });
  });

  await group('service-only RPCs, RLS and legacy-dispatch fail-closed grants', async () => {
    const funcs = await db.query(`select proname,prosecdef,proconfig,
      has_function_privilege('anon',oid,'execute') as anon_exec,
      has_function_privilege('authenticated',oid,'execute') as auth_exec,
      has_function_privilege('service_role',oid,'execute') as svc_exec
      from pg_proc where proname in ('reserve_and_dispatch_code_task','reserve_code_provider_call',
        'begin_code_provider_call','settle_code_provider_call','release_code_provider_call','refund_code_task_if_unstarted','reconcile_code_provider_lease')`);
    assert.equal(funcs.rows.length, 7);
    for (const fn of funcs.rows) {
      assert.equal(fn.prosecdef, true, fn.proname);
      assert.ok(fn.proconfig.includes('search_path=""'), fn.proname);
      assert.equal(fn.anon_exec, false); assert.equal(fn.auth_exec, false); assert.equal(fn.svc_exec, true);
    }
    assert.equal((await one(`select has_function_privilege('service_role',
      'public.dispatch_code_task(uuid,uuid,uuid,jsonb,text,integer)','execute') as allowed`)).allowed, false);
    const security = await one(`select relrowsecurity,relforcerowsecurity,
      has_table_privilege('service_role',oid,'select') as direct from pg_class where relname='code_provider_call_reservations'`);
    assert.equal(security.relrowsecurity, true); assert.equal(security.relforcerowsecurity, true); assert.equal(security.direct, false);
    const aggregateSecurity = await db.query(`select relname,relrowsecurity,relforcerowsecurity,
      has_table_privilege('service_role',oid,'select') as direct from pg_class
      where relname in ('code_provider_global_daily','code_provider_account_daily')`);
    assert.equal(aggregateSecurity.rows.length, 2);
    for (const row of aggregateSecurity.rows) {
      assert.equal(row.relrowsecurity, true); assert.equal(row.relforcerowsecurity, true); assert.equal(row.direct, false);
    }
    const mutationTrigger = await one(`select tgtype from pg_trigger where tgname='account_code_provider_daily' and not tgisinternal`);
    assert.equal(mutationTrigger.tgtype & 8, 0, 'Deletion cannot acquire accounting/global locks or decrement retained cost');
    const deletion = await one(`select prosrc,prosecdef,proconfig,
      has_function_privilege('anon',oid,'execute') as anon_exec,
      has_function_privilege('authenticated',oid,'execute') as auth_exec,
      has_function_privilege('service_role',oid,'execute') as svc_exec
      from pg_proc where oid='public.delete_user_account(uuid,text)'::regprocedure`);
    assert.equal(deletion.prosecdef, true); assert.ok(deletion.proconfig.includes('search_path=""'));
    assert.equal(deletion.anon_exec, false); assert.equal(deletion.auth_exec, false); assert.equal(deletion.svc_exec, true);
    assert.ok(deletion.prosrc.indexOf('from public.users where id=p_user_id for update') < deletion.prosrc.indexOf('insert into public.account_storage_deletion_jobs'));
    await db.exec('set local role anon');
    await db.exec('savepoint anon_denied');
    await assert.rejects(rpc('refund_code_task_if_unstarted', [randomUUID(), user]), /permission denied/);
    await db.exec('rollback to savepoint anon_denied; reset role');
    const t = await task({ dispatch: false });
    await db.exec('set local role service_role');
    assert.equal((await dispatchTask(t)).outcome, 'dispatched');
    await db.exec('reset role');
  });
  console.log(`Verified ${groups} substantive SQL scenarios in PGlite. Multiple-session lock/concurrency and live Supabase execution remain separate gates.`);
} catch (error) {
  console.error(`SQL verification failed: ${error.code || error.name}: ${error.message}`);
  for (const line of String(error.stack || '').split('\n').filter(line => line.includes('verify-code-budget-sql.mjs'))) console.error(line);
  process.exitCode = 1;
} finally { await db.close(); }
