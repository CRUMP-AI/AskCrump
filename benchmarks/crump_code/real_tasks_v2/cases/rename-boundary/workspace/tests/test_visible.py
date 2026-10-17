import unittest
import asyncio
from inventory import paths
class Visible(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(paths(""),[])
