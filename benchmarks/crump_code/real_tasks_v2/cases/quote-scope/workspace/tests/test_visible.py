import unittest
import asyncio
from scope import digest
class Visible(unittest.TestCase):
    def test_digest(self):
        self.assertEqual(len(digest({"owner":"u"})),64)
