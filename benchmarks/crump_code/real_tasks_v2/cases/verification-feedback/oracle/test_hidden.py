import sys
sys.path.insert(0,sys.argv.pop(1))
import unittest
import asyncio

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

if __name__=="__main__": unittest.main(verbosity=2)
