"""Authoring source for ORIGINAL sanitized reductions, never a model runner.

Run only when intentionally creating/reviewing a new corpus freeze. The evaluator
pins the manifest digest independently, so regeneration cannot silently change it.
"""
from pathlib import Path
import hashlib
import json
import textwrap

ROOT = Path(__file__).resolve().parent
HARDENING = "f69e1fb5"  # Expanded and checked against local Git at authoring time.
CASES = []


def add(identifier, title, category, objective, before, after, hidden, visible,
        commit=HARDENING, paths=("backend/code_runner.py",), rationale="Code lifecycle hardening", kind="history-adapted"):
    CASES.append(dict(id=identifier, title=title, category=category, objective=objective,
                      before=before, after=after, hidden=hidden, visible=visible,
                      commit=commit, paths=paths, rationale=rationale, kind=kind))


add("activity-latest", "Merge asynchronous activity snapshots", "multi-file/lifecycle",
    "Repair merge.py and view.py. A task may appear in multiple asynchronous reads. Keep the snapshot with the newest stamp (later read wins a tie), then show active tasks before terminal tasks, newest first within each group. Exclude undispatched queued drafts, ignore missing IDs, respect limit, and do not mutate inputs.",
    {"merge.py": '''
def merge(*batches):
    found = {}
    for batch in batches:
        for item in batch:
            if item.get("id") and item["id"] not in found:
                found[item["id"]] = item
    return list(found.values())
''', "view.py": '''
from merge import merge
ACTIVE = {"queued", "running", "verifying"}
def activity(batches, limit=18):
    rows = merge(*batches)
    return sorted(rows, key=lambda row: row["stamp"], reverse=True)[:limit]
'''},
    {"merge.py": '''
from copy import deepcopy
def merge(*batches):
    found = {}
    for batch in batches:
        for item in batch:
            key = item.get("id")
            if key and (key not in found or item["stamp"] >= found[key]["stamp"]):
                found[key] = deepcopy(item)
    return list(found.values())
''', "view.py": '''
from merge import merge
ACTIVE = {"queued", "running", "verifying"}
def activity(batches, limit=18):
    rows = [row for row in merge(*batches)
            if row["status"] != "queued" or row.get("paid")]
    return sorted(rows, key=lambda row: (row["status"] not in ACTIVE, -row["stamp"]))[:max(0, limit)]
'''},
    '''
from merge import merge
from view import activity
class Hidden(unittest.TestCase):
    def test_latest_and_detached(self):
        a = {"id":"a", "stamp":1,"status":"running","detail":{"n":1}}
        b = {"id":"a", "stamp":3,"status":"completed","detail":{"n":2}}
        result = merge([a],[b])
        self.assertEqual(result[0]["status"],"completed")
        result[0]["detail"]["n"] = 90
        self.assertEqual(b["detail"]["n"],2)
    def test_tie_uses_later_read(self):
        self.assertEqual(merge([{"id":"x","stamp":4,"status":"running"}],
          [{"id":"x","stamp":4,"status":"failed"}])[0]["status"],"failed")
    def test_group_limit_and_drafts(self):
        rows = [{"id":"done","stamp":9,"status":"completed"},
          {"id":"draft","stamp":10,"status":"queued"},
          {"id":"live","stamp":2,"status":"running"},
          {"id":"paid","stamp":3,"status":"queued","paid":True},
          {"stamp":30,"status":"running"}]
        self.assertEqual([r["id"] for r in activity([rows],2)],["paid","live"])
        self.assertEqual(activity([rows],0),[])
''', 'from merge import merge\nclass Visible(unittest.TestCase):\n    def test_one_batch(self):\n        self.assertEqual(len(merge([{"id":"a","stamp":1}])),1)\n',
    commit="323dfb4c", paths=("backend/code_service.py",), rationale="Original reduction of freshest-snapshot activity reconciliation and bounded ordering.")

add("gateway-retry", "Recover only safe transient reads", "async/retry",
    "Fix transport.request(send, method, max_attempts=4). send is async and yields an HTTP status or raises ConnectionError. Retry GET/HEAD on connection failures and 408/500/502/503/504/520 up to the bound, yielding between attempts. Never retry another method or permanent status; propagate an exhausted connection error.",
    {"transport.py": '''
async def request(send, method, max_attempts=4):
    for attempt in range(max_attempts):
        status = await send()
        if status not in {503,504} or attempt == max_attempts-1:
            return status
'''},
    {"transport.py": '''
import asyncio
async def request(send, method, max_attempts=4):
    allowed = method.upper() in {"GET", "HEAD"}
    for attempt in range(max(1, max_attempts)):
        try:
            status = await send()
        except ConnectionError:
            if not allowed or attempt == max(1,max_attempts)-1:
                raise
        else:
            if not allowed or status not in {408,500,502,503,504,520} or attempt == max(1,max_attempts)-1:
                return status
        await asyncio.sleep(0)
'''},
    '''
from transport import request
class Hidden(unittest.IsolatedAsyncioTestCase):
    async def test_gateway_and_transport(self):
        items=[ConnectionError(),502,500,200]; seen=[]
        async def send():
            value=items.pop(0); seen.append(value)
            if isinstance(value,Exception): raise value
            return value
        self.assertEqual(await request(send,"get"),200)
        self.assertEqual(len(seen),4)
    async def test_writes_permanent_and_bound(self):
        for method,status,expected in [("POST",503,1),("GET",400,1),("HEAD",502,3)]:
            calls=[]
            async def send(): calls.append(1); return status
            self.assertEqual(await request(send,method,3),status)
            self.assertEqual(len(calls),expected)
    async def test_exhausted_connection(self):
        calls=[]
        async def send(): calls.append(1); raise ConnectionError("offline")
        with self.assertRaises(ConnectionError): await request(send,"GET",2)
        self.assertEqual(len(calls),2)
''', 'from transport import request\nclass Visible(unittest.IsolatedAsyncioTestCase):\n    async def test_success(self):\n        async def send(): return 200\n        self.assertEqual(await request(send,"GET"),200)\n',
    commit="249da8f4", paths=("backend/db.py",), rationale="Transient gateway recovery distinguishes safe reads from writes.")

add("sync-write-replay", "Retry an idempotent sync boundary", "multi-file/async",
    "Fix sync.push and store.MemoryStore. Replaying the same owner/chat/revision after a dropped response must not append another conversation. A newer revision replaces its value; an older/equal revision is ignored. push must opt in to the transport's retry_transient switch, preserve owner isolation and return the accepted/ignored result.",
    {"sync.py": '''
async def push(db, owner, item):
    return await db.write(owner, dict(item), retry_transient=False)
''', "store.py": '''
class MemoryStore:
    def __init__(self): self.rows = []
    async def apply(self, owner, item):
        self.rows.append({"owner":owner, **item})
        return "accepted"
'''},
    {"sync.py": '''
async def push(db, owner, item):
    return await db.write(owner, dict(item), retry_transient=True)
''', "store.py": '''
import asyncio
from copy import deepcopy
class MemoryStore:
    def __init__(self): self.rows = []; self.lock=asyncio.Lock()
    async def apply(self, owner, item):
        async with self.lock:
            for index,row in enumerate(self.rows):
                if row["owner"]==owner and row["id"]==item["id"]:
                    if row["revision"]>=item["revision"]: return "ignored"
                    self.rows[index]={**deepcopy(item),"owner":owner}; return "accepted"
            self.rows.append({**deepcopy(item),"owner":owner}); return "accepted"
'''},
    '''
from sync import push
from store import MemoryStore
class Hidden(unittest.IsolatedAsyncioTestCase):
    async def test_lost_response_replay(self):
        store=MemoryStore()
        class DB:
            async def write(self,owner,item,*,retry_transient):
                first=await store.apply(owner,item)
                if not retry_transient: raise ConnectionError("dropped after commit")
                return await store.apply(owner,item)
        self.assertEqual(await push(DB(),"u",{"id":"x","revision":1,"text":"a"}),"ignored")
        self.assertEqual(len(store.rows),1)
    async def test_revision_and_owner(self):
        store=MemoryStore()
        self.assertEqual(await store.apply("u",{"id":"x","revision":2}),"accepted")
        self.assertEqual(await store.apply("u",{"id":"x","revision":1}),"ignored")
        self.assertEqual(await store.apply("v",{"id":"x","revision":1}),"accepted")
        self.assertEqual(len(store.rows),2)
''', 'from store import MemoryStore\nclass Visible(unittest.IsolatedAsyncioTestCase):\n    async def test_first(self):\n        self.assertEqual(await MemoryStore().apply("u",{"id":"x","revision":1}),"accepted")\n',
    commit="54c5255e", paths=("backend/sync_service.py",), rationale="Explicit idempotent retry at compare-and-apply sync and settings boundaries.")

add("quote-scope", "Bind credit confirmation to exact work", "multi-file/security",
    "Fix scope.digest and dispatch.authorized. Scope hashing must be deterministic canonical JSON, independent of dictionary insertion order. A 12-credit confirmation is valid only for exactly this owner, task ID, and mode; reject any changed field and every non-integer/bool/insufficient amount before calling charge. Return the canonical charge receipt unchanged.",
    {"scope.py": '''
import hashlib
def digest(scope): return hashlib.sha256(str(scope).encode()).hexdigest()
''', "dispatch.py": '''
from scope import digest
async def authorized(task, confirmation, charge):
    if confirmation["scope"] != digest({"owner":task["owner"]}): raise ValueError("scope")
    return await charge(confirmation["credits"])
'''},
    {"scope.py": '''
import hashlib
import json
def digest(scope):
    return hashlib.sha256(json.dumps(scope,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
''', "dispatch.py": '''
from scope import digest
async def authorized(task, confirmation, charge):
    expected={key:task[key] for key in ("owner","id","mode")}
    if confirmation.get("scope") != digest(expected): raise ValueError("scope")
    amount=confirmation.get("credits")
    if type(amount) is not int or amount != 12: raise ValueError("credits")
    return await charge(12)
'''},
    '''
from scope import digest
from dispatch import authorized
class Hidden(unittest.IsolatedAsyncioTestCase):
    async def test_valid_canonical_receipt(self):
        task={"owner":"u","id":"a","mode":"plan"}; receipt={"id":"ledger","credits":12}; calls=[]
        async def charge(n): calls.append(n); return receipt
        self.assertIs(await authorized(task,{"scope":digest(dict(reversed(list(task.items())))),"credits":12},charge),receipt)
        self.assertEqual(calls,[12])
    async def test_changed_scope_has_zero_charge(self):
        task={"owner":"u","id":"a","mode":"plan"}; calls=[]
        async def charge(n): calls.append(n)
        confirmation={"scope":digest(task),"credits":12}
        for field,value in [("owner","v"),("id","b"),("mode","implement")]:
            with self.assertRaises(ValueError): await authorized({**task,field:value},confirmation,charge)
        self.assertEqual(calls,[])
    async def test_invalid_credit_types(self):
        task={"owner":"u","id":"a","mode":"plan"}
        async def charge(n): self.fail("invalid amount charged")
        for n in [True,12.0,"12",0,11,13]:
            with self.assertRaises(ValueError): await authorized(task,{"scope":digest(task),"credits":n},charge)
''', 'from scope import digest\nclass Visible(unittest.TestCase):\n    def test_digest(self):\n        self.assertEqual(len(digest({"owner":"u"})),64)\n', paths=("backend/code_service.py",), rationale="Task/mode-scoped credit authorization before atomic dispatch; fixture uses an original digest envelope, not production tokens.")

add("provider-retry", "Do not replay accepted provider work", "multi-file/async",
    "Fix policy.retryable and worker.process. A provider_started marker forbids any automatic retry, including unexpected exceptions. Before it starts, retry only declared transient failures below max_attempts; missing/unknown failures terminate. process returns completed on success, retrying on a permitted retry and failed otherwise, with one run invocation.",
    {"policy.py": '''
def retryable(task, code):
    return task["attempt"] < task["maximum"] and code in {"timeout","network"}
''', "worker.py": '''
from policy import retryable
async def process(task, run):
    try: await run(); return "completed"
    except TimeoutError: return "retrying" if retryable(task,"timeout") else "failed"
    except Exception: return "retrying"
'''},
    {"policy.py": '''
def retryable(task, code):
    return not task.get("provider_started") and task["attempt"] < task["maximum"] and code in {"timeout","network"}
''', "worker.py": '''
from policy import retryable
async def process(task, run):
    try: await run(); return "completed"
    except TimeoutError: return "retrying" if retryable(task,"timeout") else "failed"
    except ConnectionError: return "retrying" if retryable(task,"network") else "failed"
    except Exception: return "failed"
'''},
    '''
from policy import retryable
from worker import process
class Hidden(unittest.IsolatedAsyncioTestCase):
    async def test_all_post_begin_failures_terminal(self):
        for error in [TimeoutError(),ConnectionError(),RuntimeError()]:
            calls=[]
            async def run(): calls.append(1); raise error
            self.assertEqual(await process({"attempt":1,"maximum":3,"provider_started":True},run),"failed")
            self.assertEqual(calls,[1])
    async def test_pre_begin_limits(self):
        task={"attempt":1,"maximum":3}
        self.assertTrue(retryable(task,"timeout")); self.assertFalse(retryable(task,"unknown"))
        self.assertFalse(retryable({**task,"attempt":3},"network"))
        async def run(): raise ConnectionError()
        self.assertEqual(await process(task,run),"retrying")
''', 'from worker import process\nclass Visible(unittest.IsolatedAsyncioTestCase):\n    async def test_success(self):\n        async def run(): return None\n        self.assertEqual(await process({"attempt":1,"maximum":3},run),"completed")\n', paths=("backend/code_worker.py",), rationale="All failure branches guard the durable first-provider marker.")

add("complete-patch", "Never return a truncated patch", "artifacts/boundaries",
    "Fix artifact.read_patch(read_bytes, limit). Return the complete UTF-8 text only when its byte count is at most limit. A larger, invalid UTF-8, missing, or non-byte artifact must raise ValueError, never yield a shortened or replacement-decoded artifact. Empty bytes are valid; bool/negative/non-integer limits are invalid.",
    {"artifact.py": '''
def read_patch(read_bytes, limit):
    return read_bytes()[:limit].decode("utf-8",errors="replace")
'''},
    {"artifact.py": '''
def read_patch(read_bytes, limit):
    if type(limit) is not int or limit < 0: raise ValueError("limit")
    try: data=read_bytes()
    except OSError as exc: raise ValueError("missing") from exc
    if not isinstance(data,bytes) or len(data)>limit: raise ValueError("incomplete")
    try: return data.decode("utf-8")
    except UnicodeError as exc: raise ValueError("encoding") from exc
'''},
    '''
from artifact import read_patch
class Hidden(unittest.TestCase):
    def test_complete_boundary(self):
        self.assertEqual(read_patch(lambda:"é".encode(),2),"é")
        self.assertEqual(read_patch(lambda:b"",0),"")
        for data,limit in [(b"abc",2),(b"\\xff",10),(None,1),("x",1)]:
            with self.assertRaises(ValueError): read_patch(lambda:data,limit)
    def test_missing_and_bad_limits(self):
        def missing(): raise FileNotFoundError()
        with self.assertRaises(ValueError): read_patch(missing,10)
        for limit in [True,-1,2.0]:
            with self.assertRaises(ValueError): read_patch(lambda:b"a",limit)
''', 'from artifact import read_patch\nclass Visible(unittest.TestCase):\n    def test_text(self):\n        self.assertEqual(read_patch(lambda:b"a",1),"a")\n', rationale="Original byte-level reduction of complete patch limit enforcement.")

add("rename-boundary", "Parse the entire NUL Git inventory", "path/security",
    "Fix inventory.paths(raw). Parse porcelain-v1 -z status: ordinary records are XY<space>path<NUL>; rename/copy records add source<NUL> after destination. Return sorted unique paths including both sides. Reject a truncated/malformed record, any .env or .git path component, absolute/traversal/backslash paths, and leading/trailing whitespace. Interior spaces are valid; empty inventory returns [].",
    {"inventory.py": '''
def paths(raw):
    return sorted({line[3:].strip().split(" -> ")[-1] for line in raw.splitlines() if line})
'''},
    {"inventory.py": '''
def paths(raw):
    if not isinstance(raw,str) or (raw and not raw.endswith("\\0")): raise ValueError("truncated")
    entries=raw.split("\\0"); output=[]; index=0
    while index<len(entries)-1:
        entry=entries[index]; index+=1
        if len(entry)<4 or entry[2]!=" " or any(c not in " MADRCU?!" for c in entry[:2]): raise ValueError("record")
        candidates=[entry[3:]]
        if "R" in entry[:2] or "C" in entry[:2]:
            if index>=len(entries)-1: raise ValueError("rename")
            candidates.append(entries[index]); index+=1
        for path in candidates:
            parts=path.split("/")
            if path!=path.strip() or "\\\\" in path or ":" in path or any(p in {"",".","..",".env",".git"} for p in parts): raise ValueError("path")
            output.append(path)
    return sorted(set(output))
'''},
    '''
from inventory import paths
class Hidden(unittest.TestCase):
    def test_space_and_rename(self):
        self.assertEqual(paths(" M name with spaces.py\\0R  new.py\\0old.py\\0"),["name with spaces.py","new.py","old.py"])
        self.assertEqual(paths(""),[])
    def test_protected_source_and_bad_inputs(self):
        for raw in ["R  safe.py\\0.env\\0"," M .git/config\\0"," M /tmp/a.py\\0","?? ../a.py\\0", "?? a\\\\b.py\\0"," M a.py", "R  a.py\\0", "bad\\0", "?? a.py \\0"]:
            with self.assertRaises(ValueError,msg=repr(raw)): paths(raw)
''', 'from inventory import paths\nclass Visible(unittest.TestCase):\n    def test_empty(self):\n        self.assertEqual(paths(""),[])\n', rationale="NUL porcelain parsing and source/destination eligibility at the artifact boundary.")

add("ignored-write", "Validate patch eligibility before writing", "async/side-effects",
    "Fix writer.write(fs, git, path, content). git.check_ignore returns async status0 ignored,1 eligible (including tracked files matching a pattern),other unknown. Reject ignored with ValueError and unknown with RuntimeError before creating a directory or writing. On1, mkdir the parent if needed then write and return the path; never reinterpret a tracked file based on pattern text.",
    {"writer.py": '''
async def write(fs, git, path, content):
    await fs.write(path,content)
    if await git.check_ignore(path)==0: raise ValueError("ignored")
    return path
'''},
    {"writer.py": '''
from pathlib import PurePosixPath
async def write(fs, git, path, content):
    status=await git.check_ignore(path)
    if status==0: raise ValueError("ignored")
    if status!=1: raise RuntimeError("eligibility unknown")
    parent=str(PurePosixPath(path).parent)
    if parent!=".": await fs.mkdir(parent)
    await fs.write(path,content)
    return path
'''},
    '''
from writer import write
class Hidden(unittest.IsolatedAsyncioTestCase):
    async def test_zero_side_effects_for_rejection(self):
        for status,error in [(0,ValueError),(128,RuntimeError)]:
            calls=[]
            class FS:
                async def write(self,*args): calls.append("write")
                async def mkdir(self,*args): calls.append("mkdir")
            class Git:
                async def check_ignore(self,path): return status
            with self.assertRaises(error): await write(FS(),Git(),"gen/a.py","x")
            self.assertEqual(calls,[])
    async def test_eligible_parent_and_order(self):
        calls=[]
        class FS:
            async def write(self,*args): calls.append(("write",args))
            async def mkdir(self,*args): calls.append(("mkdir",args))
        class Git:
            async def check_ignore(self,path): calls.append(("check",path)); return 1
        self.assertEqual(await write(FS(),Git(),"src/a.py","x"),"src/a.py")
        self.assertEqual([c[0] for c in calls],["check","mkdir","write"])
''', 'from writer import write\nclass Visible(unittest.TestCase):\n    def test_async_api(self):\n        import inspect\n        self.assertTrue(inspect.iscoroutinefunction(write))\n', rationale="Original no-side-effect reduction of ignored-file rejection before source writes.")

add("expiry-projection", "Retain private fields for expiry reconciliation", "multi-file/data-boundary",
    "Fix query.list_tasks and lifecycle.expire. DB projection is real: it returns only requested fields. Reconcile expired rows using owner, receipt and lease, mark paid unstarted work refund_pending, and use the lease as an optimistic filter. Public results contain only id/status/failure_code. Unexpired rows must not be written; preserve canonical owner and never leak receipt/lease.",
    {"query.py": '''
from lifecycle import expire
async def list_tasks(db,now):
    rows=await db.select(["id","status","expires"])
    return [await expire(db,row,now) for row in rows]
''', "lifecycle.py": '''
async def expire(db,row,now):
    if row["expires"]<=now:
        return await db.update(row["id"],row["owner"],{}, {"status":"cancelled","failure_code":"expired"})
    return row
'''},
    {"query.py": '''
from lifecycle import expire
async def list_tasks(db,now):
    rows=await db.select(["id","owner","status","expires","receipt","lease"])
    result=[await expire(db,row,now) for row in rows]
    return [{key:row[key] for key in ("id","status","failure_code") if key in row} for row in result]
''', "lifecycle.py": '''
async def expire(db,row,now):
    if row["expires"]<=now:
        changes={"status":"cancelled","failure_code":"expired"}
        if row.get("receipt"): changes["payment_source"]="refund_pending"
        filters={"lease":row["lease"]} if row.get("lease") else {}
        return await db.update(row["id"],row["owner"],filters,changes)
    return row
'''},
    '''
from query import list_tasks
class Hidden(unittest.IsolatedAsyncioTestCase):
    async def test_projection_and_refund(self):
        row={"id":"a","owner":"u","status":"running","expires":2,"receipt":{"id":"r"},"lease":"l"}; calls=[]
        class DB:
            async def select(self,fields): return [{k:row[k] for k in fields}]
            async def update(self,id,owner,filters,changes):
                calls.append((id,owner,filters,changes)); return {**row,**changes}
        result=await list_tasks(DB(),3)
        self.assertEqual(result,[{"id":"a","status":"cancelled","failure_code":"expired"}])
        self.assertEqual(calls[0][:3],("a","u",{"lease":"l"}))
        self.assertEqual(calls[0][3]["payment_source"],"refund_pending")
    async def test_unexpired_public_projection(self):
        row={"id":"a","owner":"u","status":"running","expires":9,"receipt":{},"lease":"l"}
        class DB:
            async def select(self,fields): return [{k:row[k] for k in fields}]
            async def update(self,*args): raise AssertionError("unexpired write")
        self.assertEqual(await list_tasks(DB(),3),[{"id":"a","status":"running"}])
''', 'from query import list_tasks\nclass Visible(unittest.TestCase):\n    def test_async_api(self):\n        import inspect\n        self.assertTrue(inspect.iscoroutinefunction(list_tasks))\n', paths=("backend/code_service.py",), rationale="Projection-aware expiry reconciliation must retain private fields internally and whitelist public output.")

add("verification-repair", "Require fresh verification after the final edit", "multi-file/verification-repair",
    "Fix workspace.Workspace and verdict.verdict. Every edit increments generation; checks record current generation, command and return code. Verdict is completed only if each required command's latest check at the FINAL generation has integer code0. Old failures can be repaired by a later passing check; checks before the last edit do not count. Empty requirements/invalid/null/bool codes cannot certify changed work. Unchanged work completes without checks.",
    {"workspace.py": '''
class Workspace:
    def __init__(self): self.generation=0; self.checks=[]
    def edit(self): self.generation+=1
    def check(self,command,code): self.checks.append({"command":command,"code":code,"generation":0})
''', "verdict.py": '''
def verdict(workspace,required):
    return "completed" if workspace.checks and all(c["code"]==0 for c in workspace.checks) else "failed"
'''},
    {"workspace.py": '''
class Workspace:
    def __init__(self): self.generation=0; self.checks=[]
    def edit(self): self.generation+=1
    def check(self,command,code): self.checks.append({"command":command,"code":code,"generation":self.generation})
''', "verdict.py": '''
def verdict(workspace,required):
    if workspace.generation==0: return "completed"
    if not required: return "failed"
    latest={}
    for check in workspace.checks:
        if check["generation"]==workspace.generation: latest[check["command"]]=check["code"]
    return "completed" if all(name in latest and type(latest[name]) is int and latest[name]==0 for name in required) else "failed"
'''},
    '''
from workspace import Workspace
from verdict import verdict
class Hidden(unittest.TestCase):
    def test_repair_uses_latest_and_generation(self):
        w=Workspace(); w.edit(); w.check("tests",1); w.edit(); w.check("tests",0)
        self.assertEqual(verdict(w,["tests"]),"completed")
        w.edit(); self.assertEqual(verdict(w,["tests"]),"failed")
    def test_all_required_and_strict_codes(self):
        for code in [None,False,0.0,1]:
            w=Workspace(); w.edit(); w.check("tests",code)
            self.assertEqual(verdict(w,["tests"]),"failed")
        w=Workspace(); w.edit(); w.check("tests",0)
        self.assertEqual(verdict(w,["tests","lint"]),"failed")
        self.assertEqual(verdict(w,[]),"failed")
        self.assertEqual(verdict(Workspace(),["tests"]),"completed")
''', 'from workspace import Workspace\nclass Visible(unittest.TestCase):\n    def test_edit_generation(self):\n        w=Workspace(); w.edit(); self.assertEqual(w.generation,1)\n',
    kind="original", commit=None, paths=(), rationale="Original verification-repair exercise; no historical-production equivalence is claimed.")

add("cancel-begin", "Serialize provider begin against cancellation", "async/concurrency",
    "Repair gate.Gate so concurrent begin/cancel have one atomic decision. begin returns True exactly when it changes ready to started. cancel returns True and refunds exactly once only when ready; after started it may mark cancelled but must never refund. Any later begin returns False. Keep state/refunds public for inspection; use no sleeps or I/O while holding a mutation boundary.",
    {"gate.py": '''
import asyncio
class Gate:
    def __init__(self): self.state="ready"; self.refunds=0
    async def begin(self):
        allowed=self.state=="ready"
        await asyncio.sleep(0)
        if allowed: self.state="started"
        return allowed
    async def cancel(self):
        refundable=self.state=="ready"
        await asyncio.sleep(0)
        self.state="cancelled"
        if refundable: self.refunds+=1
        return refundable
'''},
    {"gate.py": '''
import asyncio
class Gate:
    def __init__(self): self.state="ready"; self.refunds=0; self.lock=asyncio.Lock()
    async def begin(self):
        async with self.lock:
            if self.state!="ready": return False
            self.state="started"; return True
    async def cancel(self):
        async with self.lock:
            refundable=self.state=="ready"
            self.state="cancelled"
            if refundable: self.refunds+=1
            return refundable
'''},
    '''
from gate import Gate
class Hidden(unittest.IsolatedAsyncioTestCase):
    async def test_race_never_starts_and_refunds(self):
        for reverse in [False,True]:
            for _ in range(12):
                g=Gate(); jobs=[g.begin(),g.cancel()]
                if reverse: jobs.reverse()
                result=await asyncio.gather(*jobs)
                started=result[1] if reverse else result[0]
                self.assertFalse(started and g.refunds)
                self.assertFalse(await g.begin())
    async def test_multiple_cancel_is_once(self):
        g=Gate(); await asyncio.gather(*(g.cancel() for _ in range(20)))
        self.assertEqual(g.refunds,1)
''', 'from gate import Gate\nclass Visible(unittest.IsolatedAsyncioTestCase):\n    async def test_sequential_begin(self):\n        self.assertTrue(await Gate().begin())\n', paths=("migrations/20261015230059_atomic_code_dispatch_provider_budget.sql",), rationale="Original async in-memory reduction of the SQL begin/refund serialization invariant.")

add("daily-retention", "Preserve daily admission history across deletion", "stateful/budget",
    "Fix ledger.Ledger. reserve(id,day,amount,cap) must reject duplicate IDs and daily overflow, preserving the strictest admitted cap. settle changes that reservation's held cost to actual (or max(reserved,actual) when uncertain); release holds0; erase removes only identifiable reservation data, not historical day totals/caps. Late settlement updates original day. Reject noninteger/negative amounts and settlement on absent IDs. totals(day) returns (held,cap) or (0,None).",
    {"ledger.py": '''
class Ledger:
    def __init__(self): self.rows={}
    def totals(self,day):
        rows=[r for r in self.rows.values() if r["day"]==day]
        return sum(r["held"] for r in rows),min((r["cap"] for r in rows),default=None)
    def reserve(self,id,day,amount,cap):
        used,oldcap=self.totals(day)
        if used+amount>cap: raise ValueError("budget")
        self.rows[id]={"day":day,"reserved":amount,"held":amount,"cap":cap}
    def settle(self,id,actual,uncertain=False): self.rows[id]["held"]=actual
    def release(self,id): self.rows[id]["held"]=0
    def erase(self,id): self.rows.pop(id)
'''},
    {"ledger.py": '''
class Ledger:
    def __init__(self): self.rows={}; self.days={}
    def totals(self,day): return self.days.get(day,(0,None))
    def reserve(self,id,day,amount,cap):
        if id in self.rows or type(amount) is not int or amount<=0 or type(cap) is not int or cap<=0: raise ValueError("admission")
        used,oldcap=self.totals(day); effective=min(cap,oldcap) if oldcap is not None else cap
        if used+amount>effective: raise ValueError("budget")
        self.rows[id]={"day":day,"reserved":amount,"held":amount,"cap":cap}
        self.days[day]=(used+amount,effective)
    def _hold(self,id,value):
        if id not in self.rows or type(value) is not int or value<0: raise ValueError("settlement")
        row=self.rows[id]; used,cap=self.days[row["day"]]
        self.days[row["day"]]=(used+value-row["held"],cap); row["held"]=value
    def settle(self,id,actual,uncertain=False):
        if id not in self.rows or type(actual) is not int or actual<0: raise ValueError("settlement")
        self._hold(id,max(self.rows[id]["reserved"],actual) if uncertain else actual)
    def release(self,id): self._hold(id,0)
    def erase(self,id): self.rows.pop(id)
'''},
    '''
from ledger import Ledger
class Hidden(unittest.TestCase):
    def test_deletion_and_minimum(self):
        l=Ledger(); l.reserve("a","today",6,10); l.erase("a")
        self.assertEqual(l.totals("today"),(6,10))
        with self.assertRaises(ValueError): l.reserve("b","today",5,30)
        self.assertEqual(l.totals("today"),(6,10))
    def test_late_usage_and_uncertainty(self):
        l=Ledger(); l.reserve("a","old",6,20); l.reserve("b","new",4,20)
        l.settle("a",9,True); self.assertEqual(l.totals("old"),(9,20))
        self.assertEqual(l.totals("new"),(4,20))
        l.release("b"); self.assertEqual(l.totals("new"),(0,20))
    def test_duplicate_and_invalid(self):
        l=Ledger(); l.reserve("a",1,3,9)
        for id,amount in [("a",2),("b",True),("b",-1)]:
            with self.assertRaises(ValueError): l.reserve(id,1,amount,9)
        with self.assertRaises(ValueError): l.settle("missing",1)
''', 'from ledger import Ledger\nclass Visible(unittest.TestCase):\n    def test_initial(self):\n        self.assertEqual(Ledger().totals("day"),(0,None))\n', paths=("migrations/20261015230059_atomic_code_dispatch_provider_budget.sql",), rationale="Deletion-independent daily budget aggregates, cap minima and original-day settlement; original Python reduction of SQL accounting.")

add("workspace-paths", "Enforce canonical source paths", "path/security",
    "Fix paths.normalize(value). Accept only nonempty canonical relative POSIX source paths ending .py/.js/.txt/.md. Reject leading/trailing whitespace, slash/backslash roots, drive names, repeated separators, dot/dotdot components, control characters and any case-insensitive .git/.env component. Return input unchanged when valid. No filesystem access belongs in this pure canonicalizer.",
    {"paths.py": '''
def normalize(value):
    value=str(value).replace("\\\\","/").strip(" /")
    if ".." in value: raise ValueError("path")
    return value
'''},
    {"paths.py": '''
def normalize(value):
    if not isinstance(value,str) or not value or value!=value.strip() or "\\\\" in value or ":" in value or any(ord(c)<32 for c in value): raise ValueError("path")
    parts=value.split("/")
    if any(p in {"",".",".."} or p.lower() in {".git",".env"} for p in parts): raise ValueError("path")
    if not value.endswith((".py",".js",".txt",".md")): raise ValueError("source")
    return value
'''},
    '''
from paths import normalize
class Hidden(unittest.TestCase):
    def test_canonical(self):
        for path in ["src/a.py","docs/a b.md","a..b.txt"]: self.assertEqual(normalize(path),path)
    def test_escapes_and_protected(self):
        for path in ["/a.py","a//b.py","a/./b.py","a/../b.py","C:/a.py","a\\\\b.py",".GIT/x.py","x/.env/a.py"," a.py","a.py ","a\\n.py",None,"img.png"]:
            with self.assertRaises(ValueError,msg=repr(path)): normalize(path)
''', 'from paths import normalize\nclass Visible(unittest.TestCase):\n    def test_source(self):\n        self.assertEqual(normalize("src/a.py"),"src/a.py")\n', rationale="Original canonical-path exercise extending the production path boundary; not a literal extracted historical test.")

add("signed-admission", "Authenticate a fixed workload envelope", "multi-file/signature-security",
    "Fix tokens.verify and admission.admit. This ORIGINAL stdlib HMAC fixture is an analogue, NOT production RS256/OIDC. Format payload_hex.signature_hex; signature is HMAC-SHA256 over payload bytes with provided key. Verify signature BEFORE trusting JSON, require a dict, strict integer exp>now and exact issuer/audience/project/team/environment policy. Return only project/team; invalid envelopes raise ValueError before provision. Policy comes from the caller, never token claims.",
    {"tokens.py": '''
import json
def verify(value,key): return json.loads(bytes.fromhex(value.split(".")[0]))
''', "admission.py": '''
from tokens import verify
async def admit(value,key,policy,now,provision):
    claims=verify(value,key)
    if claims["exp"]<now: raise ValueError("expired")
    return await provision(claims)
'''},
    {"tokens.py": '''
import hashlib
import hmac
import json
def verify(value,key):
    try:
        if not isinstance(value,str) or len(value)>8192: raise ValueError("token")
        payload,signature=value.split(".")
        data=bytes.fromhex(payload); supplied=bytes.fromhex(signature)
        expected=hmac.new(key,data,hashlib.sha256).digest()
        if not hmac.compare_digest(supplied,expected): raise ValueError("signature")
        claims=json.loads(data)
        if not isinstance(claims,dict): raise ValueError("claims")
        return claims
    except (ValueError,TypeError,KeyError,UnicodeError) as exc: raise ValueError("identity") from exc
''', "admission.py": '''
from tokens import verify
async def admit(value,key,policy,now,provision):
    claims=verify(value,key)
    if type(claims.get("exp")) is not int or claims["exp"]<=now: raise ValueError("expired")
    if any(claims.get(name)!=policy[name] for name in ("issuer","audience","project","team","environment")): raise ValueError("binding")
    return await provision({name:policy[name] for name in ("project","team")})
'''},
    '''
import hashlib,hmac,json
from admission import admit
class Hidden(unittest.IsolatedAsyncioTestCase):
    async def test_valid_projection(self):
        policy={k:k+"-expected" for k in ("issuer","audience","project","team","environment")}; seen=[]
        async def provision(value): seen.append(value); return "ok"
        claims={**policy,"exp":101,"untrusted":"extra"}; data=json.dumps(claims).encode(); key=b"public-fixture-key"
        value=data.hex()+"."+hmac.new(key,data,hashlib.sha256).hexdigest()
        self.assertEqual(await admit(value,key,policy,100,provision),"ok")
        self.assertEqual(seen,[{k:policy[k] for k in ("project","team")}])
    async def test_signature_and_each_binding(self):
        policy={k:k for k in ("issuer","audience","project","team","environment")}; key=b"public-fixture-key"
        async def provision(value): self.fail("invalid identity provisioned")
        for change in [{"exp":100},{"exp":True},*({k:"wrong"} for k in policy),{"forge":True}]:
            claims={**policy,"exp":200,**change}; data=json.dumps(claims).encode()
            signature=hmac.new(b"wrong" if change.get("forge") else key,data,hashlib.sha256).hexdigest()
            with self.assertRaises(ValueError): await admit(data.hex()+"."+signature,key,policy,100,provision)
''', 'from tokens import verify\nclass Visible(unittest.TestCase):\n    def test_invalid(self):\n        with self.assertRaises(ValueError): verify("broken",b"public-key")\n', paths=("backend/code_identity.py",), rationale="Original HMAC analogue tests trust-before-side-effects, not production OIDC interoperability or cryptographic parity.", kind="original-analogue")

add("request-cost", "Reserve the whole model request", "budget/encoding",
    "Fix budget.reserve(body, policy). Exact model must match; max_tokens strict int1..max_output; UTF-8 canonical JSON of ALL fields (including tools/system) must fit max_bytes and reject NaN. Price ceiling is ceil(((bytes+4096)*input_rate + max_tokens*output_rate)/1_000_000). Return digest/cost/input_ceiling; reject ceiling above call_limit, invalid shape or nonpositive limits/rates. Never mutate body.",
    {"budget.py": '''
import hashlib,json
def reserve(body,policy):
    data=json.dumps(body.get("messages",[])).encode()
    cost=(len(data)*policy["input_rate"]+body["max_tokens"]*policy["output_rate"])//1000000
    return hashlib.sha256(data).hexdigest(),cost,len(data)
'''},
    {"budget.py": '''
import hashlib,json
def reserve(body,policy):
    try:
        if not isinstance(body,dict) or body.get("model")!=policy["model"]: raise ValueError("model")
        for field in ("max_output","max_bytes","input_rate","output_rate","call_limit"):
            if type(policy[field]) is not int or policy[field]<=0: raise ValueError("policy")
        output=body.get("max_tokens")
        if type(output) is not int or not 1<=output<=policy["max_output"]: raise ValueError("output")
        data=json.dumps(body,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()
        if len(data)>policy["max_bytes"]: raise ValueError("bytes")
        ceiling=len(data)+4096
        cost=(ceiling*policy["input_rate"]+output*policy["output_rate"]+999999)//1000000
        if cost>policy["call_limit"]: raise ValueError("budget")
        return hashlib.sha256(data).hexdigest(),cost,ceiling
    except (TypeError,KeyError,UnicodeError) as exc: raise ValueError("request") from exc
'''},
    '''
from budget import reserve
class Hidden(unittest.TestCase):
    def setUp(self):
        self.p={"model":"fixed","max_output":100,"max_bytes":1000,"input_rate":3,"output_rate":7,"call_limit":100}
        self.b={"model":"fixed","max_tokens":20,"messages":[],"system":"é"}
    def test_every_field_and_canonical_digest(self):
        first=reserve(self.b,self.p); self.assertGreater(first[2],4096)
        self.assertEqual(reserve(dict(reversed(list(self.b.items()))),self.p),first)
        self.assertNotEqual(reserve({**self.b,"tools":[{"name":"read"}]},self.p)[0],first[0])
        self.assertEqual(first[1],(first[2]*3+20*7+999999)//1000000)
    def test_rejections(self):
        for body in [{**self.b,"model":"other"},{**self.b,"max_tokens":True},{**self.b,"max_tokens":101},{**self.b,"x":float("nan")},{**self.b,"system":"a"*1001}]:
            with self.assertRaises(ValueError): reserve(body,self.p)
        with self.assertRaises(ValueError): reserve(self.b,{**self.p,"call_limit":0})
''', 'from budget import reserve\nclass Visible(unittest.TestCase):\n    def test_callable(self):\n        self.assertTrue(callable(reserve))\n', paths=("backend/code_budget.py",), rationale="Complete request-body hashing, UTF-8 upper bound and integer ceiling admission.")

add("call-lease", "Make provider begin a one-owner transition", "async/concurrency",
    "Fix calls.Calls. reserve(key,digest,lease) is idempotent only for the same digest while still reserved; a new lease may take that unused reservation. begin(key,lease) atomically returns True once for current owner, sets started, and later begins always return False. Wrong owners/different digest/reserving a started call raise ValueError without mutations. At most one concurrent begin may win.",
    {"calls.py": '''
import asyncio
class Calls:
    def __init__(self): self.rows={}
    async def reserve(self,key,digest,lease):
        self.rows[key]={"digest":digest,"lease":lease,"status":"reserved"}
        return dict(self.rows[key])
    async def begin(self,key,lease):
        allowed=self.rows[key]["status"]=="reserved"
        await asyncio.sleep(0)
        self.rows[key]["status"]="started"
        return allowed
'''},
    {"calls.py": '''
import asyncio
class Calls:
    def __init__(self): self.rows={}; self.lock=asyncio.Lock()
    async def reserve(self,key,digest,lease):
        async with self.lock:
            if key in self.rows:
                row=self.rows[key]
                if row["digest"]!=digest or row["status"]!="reserved": raise ValueError("replay")
                row["lease"]=lease
            else: self.rows[key]={"digest":digest,"lease":lease,"status":"reserved"}
            return dict(self.rows[key])
    async def begin(self,key,lease):
        async with self.lock:
            row=self.rows[key]
            if row["lease"]!=lease: raise ValueError("owner")
            if row["status"]!="reserved": return False
            row["status"]="started"; return True
'''},
    '''
from calls import Calls
class Hidden(unittest.IsolatedAsyncioTestCase):
    async def test_exactly_one_begin(self):
        c=Calls(); await c.reserve("a","digest","l")
        self.assertEqual(sum(await asyncio.gather(*(c.begin("a","l") for _ in range(30)))),1)
        with self.assertRaises(ValueError): await c.reserve("a","digest","l2")
    async def test_takeover_and_conflict_do_not_rewrite(self):
        c=Calls(); await c.reserve("a","d","l1"); await c.reserve("a","d","l2")
        before=dict(c.rows["a"])
        with self.assertRaises(ValueError): await c.reserve("a","other","l3")
        self.assertEqual(c.rows["a"],before)
        with self.assertRaises(ValueError): await c.begin("a","l1")
        self.assertTrue(await c.begin("a","l2"))
''', 'from calls import Calls\nclass Visible(unittest.IsolatedAsyncioTestCase):\n    async def test_first(self):\n        c=Calls(); self.assertEqual((await c.reserve("a","d","l"))["status"],"reserved")\n', paths=("migrations/20261015230059_atomic_code_dispatch_provider_budget.sql",), rationale="Stable call digest, pre-start lease handoff and one-time provider-begin ownership.")

add("timezone-expiry", "Compare expiry in a single time domain", "time/boundaries",
    "Fix clock.expired(value, now). Parse ISO8601 expiry including Z and offsets, treat naive expiry as UTC, compare equality as expired. now is an aware datetime. Missing/malformed/non-string expiry fails closed as expired. Do not compare strings or discard time zones; do not consult real current time.",
    {"clock.py": '''
def expired(value,now):
    return str(value)<=now.isoformat()
'''},
    {"clock.py": '''
from datetime import datetime,timezone
def expired(value,now):
    if not isinstance(value,str) or not value.strip(): return True
    try: stamp=datetime.fromisoformat(value.replace("Z","+00:00"))
    except ValueError: return True
    if stamp.tzinfo is None: stamp=stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc)<=now.astimezone(timezone.utc)
'''},
    '''
from datetime import datetime,timezone
from clock import expired
class Hidden(unittest.TestCase):
    def test_offsets_and_equal(self):
        now=datetime(2026,1,1,12,tzinfo=timezone.utc)
        for value in ["2026-01-01T13:00:00+01:00","2026-01-01T12:00:00Z","2026-01-01T12:00:00"]: self.assertTrue(expired(value,now))
        self.assertFalse(expired("2026-01-01T07:01:00-05:00",now))
    def test_invalid(self):
        now=datetime(2026,1,1,tzinfo=timezone.utc)
        for value in [None,"","invalid",1]: self.assertTrue(expired(value,now))
''', 'from datetime import datetime,timezone\nfrom clock import expired\nclass Visible(unittest.TestCase):\n    def test_old(self):\n        self.assertTrue(expired("2000-01-01T00:00:00Z",datetime(2026,1,1,tzinfo=timezone.utc)))\n', kind="original", commit=None, paths=(), rationale="Original fail-closed timezone exercise; production malformed-timestamp policy differs and is not claimed as its historical behavior.")

add("image-size", "Respect edge and pixel limits together", "numerical/boundaries",
    "Fix sizing.prepare(width,height,max_edge,max_pixels,encoded_bytes,max_bytes). Validate strict positive integer dimensions/limits and nonnegative integer byte count. Reject encoded_bytes>=max_bytes. Downscale only: one aspect-preserving scale=min(1,edge/maxdimension,sqrt(pixelcap/area)), floor each result with minimum1; final area and edge must fit, never upscale. No image library or I/O needed.",
    {"sizing.py": '''
def prepare(width,height,max_edge,max_pixels,encoded_bytes,max_bytes):
    scale=min(1,max_edge/max(width,height))
    return round(width*scale),round(height*scale)
'''},
    {"sizing.py": '''
import math
def prepare(width,height,max_edge,max_pixels,encoded_bytes,max_bytes):
    if any(type(v) is not int or v<=0 for v in (width,height,max_edge,max_pixels,max_bytes)) or type(encoded_bytes) is not int or encoded_bytes<0 or encoded_bytes>=max_bytes: raise ValueError("image bounds")
    scale=min(1,max_edge/max(width,height),math.sqrt(max_pixels/(width*height)))
    w=max(1,math.floor(width*scale)); h=max(1,math.floor(height*scale))
    if w*h>max_pixels or max(w,h)>max_edge: raise ValueError("unrepresentable bounds")
    return w,h
'''},
    '''
from sizing import prepare
class Hidden(unittest.TestCase):
    def test_square_pixel_cap_and_portrait(self):
        self.assertEqual(prepare(4000,4000,4096,4_000_000,10,100),(2000,2000))
        self.assertEqual(prepare(1000,3000,2000,4_000_000,10,100),(666,2000))
        self.assertEqual(prepare(40,20,2000,4_000_000,10,100),(40,20))
    def test_bytes_boundary_and_dimensions(self):
        for args in [(10,10,20,400,100,100),(True,10,20,400,0,100),(0,10,20,400,0,100),(10,10,20,400,-1,100)]:
            with self.assertRaises(ValueError): prepare(*args)
''', 'from sizing import prepare\nclass Visible(unittest.TestCase):\n    def test_no_upscale(self):\n        self.assertEqual(prepare(10,20,100,10000,1,100),(10,20))\n', commit="f8feca89", paths=("backend/media_service.py",), rationale="Aspect-preserving maximum edge plus pixel cap, floor rounding and encoded-byte rejection; original stdlib numeric reduction.")

add("image-recovery", "Preserve only server-shaped recovery metadata", "data/security",
    "Fix recovery.sanitize(item). Return a fresh dict with role/content only, plus recognized replyErrorCode/replyRecovery for USER messages. Codes IMAGE_SAFETY_REJECTED expect changeRequired prompt_or_reference; INVALID_IMAGE_EDIT_SOURCE/IMAGE_EDIT_SOURCE_TOO_LARGE expect reference. Recovery action must be revise_image_request and usageRestored strictly True. Missing changeRequired on old records defaults by code; a mismatched value is rejected. Drop arbitrary metadata and never mutate input.",
    {"recovery.py": '''
def sanitize(item):
    return dict(item)
'''},
    {"recovery.py": '''
def sanitize(item):
    result={"role":item["role"],"content":item.get("content","")}
    expected={"IMAGE_SAFETY_REJECTED":"prompt_or_reference","INVALID_IMAGE_EDIT_SOURCE":"reference","IMAGE_EDIT_SOURCE_TOO_LARGE":"reference"}
    code=item.get("replyErrorCode")
    if item["role"]=="user" and code in expected:
        result["replyErrorCode"]=code; r=item.get("replyRecovery")
        if isinstance(r,dict) and r.get("action")=="revise_image_request" and r.get("usageRestored") is True and r.get("changeRequired",expected[code])==expected[code]:
            result["replyRecovery"]={"action":"revise_image_request","usageRestored":True,"changeRequired":expected[code]}
    return result
'''},
    '''
from copy import deepcopy
from recovery import sanitize
class Hidden(unittest.TestCase):
    def test_legacy_recovery_detached_whitelist(self):
        item={"role":"user","content":"edit","replyErrorCode":"INVALID_IMAGE_EDIT_SOURCE","replyRecovery":{"action":"revise_image_request","usageRestored":True,"extra":"no"},"approved":True}
        original=deepcopy(item); result=sanitize(item)
        self.assertEqual(result["replyRecovery"]["changeRequired"],"reference")
        self.assertNotIn("approved",result); self.assertNotIn("extra",result["replyRecovery"])
        result["replyRecovery"]["usageRestored"]=False; self.assertEqual(item,original)
    def test_reject_bad_role_code_type_and_change(self):
        base={"role":"user","content":"x","replyErrorCode":"IMAGE_SAFETY_REJECTED","replyRecovery":{"action":"revise_image_request","usageRestored":True}}
        for change in [{"role":"assistant"},{"replyErrorCode":"UNKNOWN"},{"replyRecovery":{"action":"revise_image_request","usageRestored":1}},{"replyRecovery":{"action":"revise_image_request","usageRestored":True,"changeRequired":"reference"}}]:
            self.assertNotIn("replyRecovery",sanitize({**base,**change}))
''', 'from recovery import sanitize\nclass Visible(unittest.TestCase):\n    def test_simple(self):\n        self.assertEqual(sanitize({"role":"user","content":"hello"}),{"role":"user","content":"hello"})\n', commit="f8feca89", paths=("backend/sync_service.py",), rationale="Persist only recognized recovery metadata while preserving earlier saved safety records.")

add("startup-order", "Arm demo transport before the shell mounts", "lifecycle/state-machine",
    "Fix startup.Boot. An armed demo installs its interceptor immediately on construction, but enters only after shell_ready or dom_ready. Any event order/repetition enters once. On dom_ready, register the demo chats renderer once even if already entered; DOM fallback permits a missing shell. Unarmed boot must never intercept, enter or register. Use callbacks, no global state.",
    {"startup.py": '''
class Boot:
    def __init__(self,armed,install,enter,register):
        self.armed=armed; self.install=install; self.enter=enter; self.register=register
        if armed: enter()
    def shell_ready(self):
        if self.armed: self.install(); self.enter()
    def dom_ready(self):
        if self.armed: self.enter(); self.register()
'''},
    {"startup.py": '''
class Boot:
    def __init__(self,armed,install,enter,register):
        self.armed=armed; self.install=install; self.enter=enter; self.register=register; self.entered=False; self.registered=False
        if armed: install()
    def _enter(self):
        if self.armed and not self.entered: self.entered=True; self.enter()
    def shell_ready(self): self._enter()
    def dom_ready(self):
        self._enter()
        if self.armed and not self.registered: self.registered=True; self.register()
'''},
    '''
from startup import Boot
class Hidden(unittest.TestCase):
    def test_ready_orders_and_once(self):
        for order in [("shell_ready","dom_ready"),("dom_ready","shell_ready")]:
            calls=[]; b=Boot(True,lambda:calls.append("install"),lambda:calls.append("enter"),lambda:calls.append("register"))
            self.assertEqual(calls,["install"])
            for event in (*order,*order): getattr(b,event)()
            self.assertEqual(calls,["install","enter","register"])
    def test_unarmed_and_dom_fallback(self):
        calls=[]; b=Boot(False,lambda:calls.append(1),lambda:calls.append(2),lambda:calls.append(3))
        b.shell_ready(); b.dom_ready(); self.assertEqual(calls,[])
        b=Boot(True,lambda:calls.append(1),lambda:calls.append(2),lambda:calls.append(3)); b.dom_ready()
        self.assertEqual(calls,[1,2,3])
''', 'from startup import Boot\nclass Visible(unittest.TestCase):\n    def test_unarmed(self):\n        calls=[]; Boot(False,lambda:calls.append(1),lambda:calls.append(2),lambda:calls.append(3))\n        self.assertEqual(calls,[])\n', commit="d80d6c3b", paths=("public/crump-vision-demo-1.0.js",), rationale="Original Python event-state reduction of interceptor-before-mount and shell/DOMContentLoaded readiness; no browser-equivalence claim.")


CASES = [case for case in CASES if case["id"] != "timezone-expiry"]
add("verification-feedback", "Repair from real verification feedback within one budget", "async/verification-repair",
    "Fix repair.run(workspace, propose, max_turns). Each iteration calls async propose(last_feedback), then async workspace.verify(). Ignore propose's success claims; only a dict receipt with strict integer returnCode0 and revision==workspace.revision completes. Feed the actual failed/stale receipt to the next propose unchanged. All attempts/repairs share max_turns; invalid/zero/bool limits reject before callbacks. On exhaustion return failed; never call propose after a verified success.",
    {"repair.py": '''
async def run(workspace,propose,max_turns):
    for turn in range(max_turns):
        claim=await propose(None)
        if claim.get("success"): return "completed"
        receipt=await workspace.verify()
        if receipt.get("returnCode")==0: return "completed"
    return "failed"
'''},
    {"repair.py": '''
async def run(workspace,propose,max_turns):
    if type(max_turns) is not int or max_turns<1: raise ValueError("turn budget")
    feedback=None
    for turn in range(max_turns):
        await propose(feedback)
        receipt=await workspace.verify()
        if isinstance(receipt,dict) and type(receipt.get("returnCode")) is int and receipt["returnCode"]==0 and receipt.get("revision")==workspace.revision:
            return "completed"
        feedback=receipt
    return "failed"
'''},
    '''
from repair import run
class Hidden(unittest.IsolatedAsyncioTestCase):
    async def test_actual_failure_reaches_next_turn_and_success_stops(self):
        receipts=[{"returnCode":1,"revision":1,"stderr":"real syntax failure"},{"returnCode":0,"revision":2}]; feedback=[]
        class W:
            revision=0
            async def verify(self): return receipts[self.revision-1]
        w=W()
        async def propose(value): feedback.append(value); w.revision+=1; return {"success":True}
        self.assertEqual(await run(w,propose,4),"completed")
        self.assertEqual(feedback,[None,receipts[0]])
    async def test_stale_and_bool_checks_share_bound(self):
        for receipt in [{"returnCode":0,"revision":0},{"returnCode":False,"revision":1},None]:
            calls=[]
            class W:
                revision=1
                async def verify(self): return receipt
            async def propose(value): calls.append(value); return {"success":True}
            self.assertEqual(await run(W(),propose,2),"failed")
            self.assertEqual(calls,[None,receipt])
    async def test_invalid_limit_no_callbacks(self):
        async def propose(value): self.fail("invalid limit called provider")
        for limit in [0,-1,True,2.0]:
            with self.assertRaises(ValueError): await run(None,propose,limit)
''', 'from repair import run\nclass Visible(unittest.TestCase):\n    def test_async_api(self):\n        import inspect\n        self.assertTrue(inspect.iscoroutinefunction(run))\n',
    kind="original", commit=None, paths=(), rationale="Original bounded verification-feedback exercise, not a historical production reproducer or actual model trial.")


def clean(value):
    return textwrap.dedent(value).lstrip("\n").rstrip()+"\n"


def build():
    import subprocess
    repo=ROOT.parents[2]
    def revision(short):
        return subprocess.check_output(["git","rev-parse",short+"^{commit}"],cwd=repo,text=True).strip()
    cases=[]
    for spec in CASES:
        identifier=spec["id"]
        base=ROOT/"cases"/identifier
        files={}
        def write(relative,content):
            data=clean(content).encode("utf-8"); target=base/relative
            target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(data)
            files[relative]=hashlib.sha256(data).hexdigest()
        for path,content in spec["before"].items(): write("workspace/"+path,content)
        for path,content in spec["after"].items(): write("reference/"+path,content)
        write("workspace/README.txt",spec["objective"]+"\n\nRun visible checks with: python3 -m unittest discover -s tests -v\nOnly the listed source modules may change. Tests and this description are immutable. Hidden acceptance checks are evaluator-owned.\nThis restricted corpus permits stdlib asyncio/copy/datetime/hashlib/hmac/json/math/collections/dataclasses/re/typing/decimal, pathlib.PurePosixPath, and sibling source modules. No filesystem/process/network I/O, harness introspection, module monkeypatches, or dynamic execution.\n")
        prefix="import unittest\nimport asyncio\n"
        write("workspace/tests/test_visible.py",prefix+spec["visible"])
        write("oracle/test_hidden.py",'import sys\nsys.path.insert(0,sys.argv.pop(1))\n'+prefix+spec["hidden"]+'\nif __name__=="__main__": unittest.main(verbosity=2)\n')
        import ast
        tree=ast.parse(clean(spec["hidden"]))
        checks=[f"Hidden.{item.name}" for node in tree.body if isinstance(node,ast.ClassDef)
                for item in node.body if isinstance(item,(ast.FunctionDef,ast.AsyncFunctionDef)) and item.name.startswith("test_")]
        # Check the provenance paths actually exist in the cited commit. These are
        # original adaptations; this never claims a verbatim historical reproducer.
        commit=revision(spec["commit"]) if spec["commit"] else None
        for path in spec["paths"]:
            subprocess.check_call(["git","cat-file","-e",f"{commit}:{path}"],cwd=repo)
        bounded={"complete-patch","ignored-write","workspace-paths","image-size","image-recovery"}
        integration={"activity-latest","gateway-retry","sync-write-replay","provider-retry","expiry-projection","startup-order"}
        stratum="bounded" if identifier in bounded else "integration" if identifier in integration else "adversarial"
        cases.append({"id":identifier,"title":spec["title"],"category":spec["category"],"stratum":stratum,
                      "verification_repair":identifier in {"verification-repair","verification-feedback"},
                      "objective":spec["objective"],"allowed_paths":sorted(spec["before"]),
                      "required_paths":sorted(path for path in spec["before"] if clean(spec["before"][path])!=clean(spec["after"][path])),
                      "provenance":{"kind":spec["kind"],"commit":commit,"paths":list(spec["paths"]),
                                    "rationale":spec["rationale"],"repository":"https://github.com/CRUMP-AI/AskCrump" if commit else None},
                      "oracle_test_ids":checks,"files":files,
                      "limits":{"patch_bytes":80000,"candidate_bytes":160000,"timeout_seconds":15},
                      "fixture_sha256":hashlib.sha256(json.dumps(files,sort_keys=True,separators=(",",":")).encode()).hexdigest()})
    assert len(cases)==20
    manifest={"schema_version":2,"suite_id":"askcrump-original-real-tasks-v2",
              "source_revision":revision(HARDENING),"language":"python-stdlib",
              "claim":"Twenty original sanitized regression exercises; cited history motivates adaptations, not literal historical reproducers or broad coding capability. No model quality result is included. Difficulty strata are author-assigned, not empirically calibrated.",
              "excluded_capabilities":["conversational clarification of ambiguous requirements","general coding parity","browser/mobile end-to-end behavior","production provider interoperability"],
              "cases":cases}
    data=(json.dumps(manifest,indent=2,ensure_ascii=False)+"\n").encode()
    (ROOT/"manifest.json").write_bytes(data)
    digest=hashlib.sha256(data).hexdigest()
    (ROOT/"freeze.sha256").write_text(digest+"\n",encoding="ascii")
    print(json.dumps({"cases":len(cases),"files":sum(len(c["files"]) for c in cases),"sha256":digest}))


if __name__=="__main__": build()
