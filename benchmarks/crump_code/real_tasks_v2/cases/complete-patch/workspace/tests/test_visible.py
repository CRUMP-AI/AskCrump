import unittest
import asyncio
from artifact import read_patch
class Visible(unittest.TestCase):
    def test_text(self):
        self.assertEqual(read_patch(lambda:b"a",1),"a")
