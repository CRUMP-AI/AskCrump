import unittest
import asyncio
from calls import Calls
class Visible(unittest.IsolatedAsyncioTestCase):
    async def test_first(self):
        c=Calls(); self.assertEqual((await c.reserve("a","d","l"))["status"],"reserved")
