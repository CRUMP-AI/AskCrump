import unittest
import asyncio
from worker import process
class Visible(unittest.IsolatedAsyncioTestCase):
    async def test_success(self):
        async def run(): return None
        self.assertEqual(await process({"attempt":1,"maximum":3},run),"completed")
