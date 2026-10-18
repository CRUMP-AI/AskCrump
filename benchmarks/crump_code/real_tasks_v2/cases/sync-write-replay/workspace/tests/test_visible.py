import unittest
import asyncio
from store import MemoryStore
class Visible(unittest.IsolatedAsyncioTestCase):
    async def test_first(self):
        self.assertEqual(await MemoryStore().apply("u",{"id":"x","revision":1}),"accepted")
