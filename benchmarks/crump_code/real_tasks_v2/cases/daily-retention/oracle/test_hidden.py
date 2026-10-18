import sys
sys.path.insert(0,sys.argv.pop(1))
import unittest
import asyncio

from ledger import Ledger
class Hidden(unittest.TestCase):
    def test_deletion_and_minimum(self):
        l=Ledger(); l.reserve("a","today",6,10); l.erase("a")
        self.assertEqual(l.totals("today"),(6,10))
        with self.assertRaises(ValueError): l.reserve("b","today",5,30)
        self.assertEqual(l.totals("today"),(6,10))
    def test_late_usage_and_uncertainty(self):
        l=Ledger(); l.reserve("a","old",6,20); l.reserve("b","new",4,20)
        l.settle("a",9,True); self.assertEqual(l.totals("old"),(9,20))
        self.assertEqual(l.totals("new"),(4,20))
        l.release("b"); self.assertEqual(l.totals("new"),(0,20))
    def test_duplicate_and_invalid(self):
        l=Ledger(); l.reserve("a",1,3,9)
        for id,amount in [("a",2),("b",True),("b",-1)]:
            with self.assertRaises(ValueError): l.reserve(id,1,amount,9)
        with self.assertRaises(ValueError): l.settle("missing",1)

if __name__=="__main__": unittest.main(verbosity=2)
