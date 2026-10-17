import unittest
import asyncio
from ledger import Ledger
class Visible(unittest.TestCase):
    def test_initial(self):
        self.assertEqual(Ledger().totals("day"),(0,None))
