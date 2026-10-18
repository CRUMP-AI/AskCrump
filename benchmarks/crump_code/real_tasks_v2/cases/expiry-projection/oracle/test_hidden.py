import sys
sys.path.insert(0,sys.argv.pop(1))
import unittest
import asyncio

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

if __name__=="__main__": unittest.main(verbosity=2)
