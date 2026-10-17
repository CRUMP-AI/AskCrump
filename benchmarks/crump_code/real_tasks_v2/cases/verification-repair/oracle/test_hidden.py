import sys
sys.path.insert(0,sys.argv.pop(1))
import unittest
import asyncio

from workspace import Workspace
from verdict import verdict
class Hidden(unittest.TestCase):
    def test_repair_uses_latest_and_generation(self):
        w=Workspace(); w.edit(); w.check("tests",1); w.edit(); w.check("tests",0)
        self.assertEqual(verdict(w,["tests"]),"completed")
        w.edit(); self.assertEqual(verdict(w,["tests"]),"failed")
    def test_all_required_and_strict_codes(self):
        for code in [None,False,0.0,1]:
            w=Workspace(); w.edit(); w.check("tests",code)
            self.assertEqual(verdict(w,["tests"]),"failed")
        w=Workspace(); w.edit(); w.check("tests",0)
        self.assertEqual(verdict(w,["tests","lint"]),"failed")
        self.assertEqual(verdict(w,[]),"failed")
        self.assertEqual(verdict(Workspace(),["tests"]),"completed")

if __name__=="__main__": unittest.main(verbosity=2)
