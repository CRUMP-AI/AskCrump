import unittest
import asyncio
from gate import Gate
class Visible(unittest.IsolatedAsyncioTestCase):
    async def test_sequential_begin(self):
        self.assertTrue(await Gate().begin())
