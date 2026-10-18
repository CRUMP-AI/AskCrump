import sys
sys.path.insert(0,sys.argv.pop(1))
import unittest
import asyncio

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

if __name__=="__main__": unittest.main(verbosity=2)
