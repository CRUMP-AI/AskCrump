import sys
sys.path.insert(0,sys.argv.pop(1))
import unittest
import asyncio

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

if __name__=="__main__": unittest.main(verbosity=2)
