import sys
sys.path.insert(0,sys.argv.pop(1))
import unittest
import asyncio

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

if __name__=="__main__": unittest.main(verbosity=2)
