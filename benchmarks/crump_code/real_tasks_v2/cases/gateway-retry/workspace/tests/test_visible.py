import unittest
import asyncio
from transport import request
class Visible(unittest.IsolatedAsyncioTestCase):
    async def test_success(self):
        async def send(): return 200
        self.assertEqual(await request(send,"GET"),200)
