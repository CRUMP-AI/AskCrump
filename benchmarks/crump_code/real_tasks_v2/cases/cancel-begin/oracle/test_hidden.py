import sys
sys.path.insert(0,sys.argv.pop(1))
import unittest
import asyncio

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

if __name__=="__main__": unittest.main(verbosity=2)
