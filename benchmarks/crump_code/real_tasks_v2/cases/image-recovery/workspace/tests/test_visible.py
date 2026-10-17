import unittest
import asyncio
from recovery import sanitize
class Visible(unittest.TestCase):
    def test_simple(self):
        self.assertEqual(sanitize({"role":"user","content":"hello"}),{"role":"user","content":"hello"})
