import unittest
import asyncio
from query import list_tasks
class Visible(unittest.TestCase):
    def test_async_api(self):
        import inspect
        self.assertTrue(inspect.iscoroutinefunction(list_tasks))
