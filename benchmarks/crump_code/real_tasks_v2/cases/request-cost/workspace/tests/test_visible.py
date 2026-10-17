import unittest
import asyncio
from budget import reserve
class Visible(unittest.TestCase):
    def test_callable(self):
        self.assertTrue(callable(reserve))
