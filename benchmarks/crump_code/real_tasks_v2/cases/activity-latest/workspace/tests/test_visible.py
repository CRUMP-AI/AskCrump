import unittest
import asyncio
from merge import merge
class Visible(unittest.TestCase):
    def test_one_batch(self):
        self.assertEqual(len(merge([{"id":"a","stamp":1}])),1)
