import unittest
import asyncio
from writer import write
class Visible(unittest.TestCase):
    def test_async_api(self):
        import inspect
        self.assertTrue(inspect.iscoroutinefunction(write))
