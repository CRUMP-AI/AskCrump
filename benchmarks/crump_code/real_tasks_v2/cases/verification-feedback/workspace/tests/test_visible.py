import unittest
import asyncio
from repair import run
class Visible(unittest.TestCase):
    def test_async_api(self):
        import inspect
        self.assertTrue(inspect.iscoroutinefunction(run))
