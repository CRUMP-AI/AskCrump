import sys
sys.path.insert(0,sys.argv.pop(1))
import unittest
import asyncio

from inventory import paths
class Hidden(unittest.TestCase):
    def test_space_and_rename(self):
        self.assertEqual(paths(" M name with spaces.py\0R  new.py\0old.py\0"),["name with spaces.py","new.py","old.py"])
        self.assertEqual(paths(""),[])
    def test_protected_source_and_bad_inputs(self):
        for raw in ["R  safe.py\0.env\0"," M .git/config\0"," M /tmp/a.py\0","?? ../a.py\0", "?? a\\b.py\0"," M a.py", "R  a.py\0", "bad\0", "?? a.py \0"]:
            with self.assertRaises(ValueError,msg=repr(raw)): paths(raw)

if __name__=="__main__": unittest.main(verbosity=2)
