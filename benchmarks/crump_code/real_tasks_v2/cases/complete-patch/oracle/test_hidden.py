import sys
sys.path.insert(0,sys.argv.pop(1))
import unittest
import asyncio

from artifact import read_patch
class Hidden(unittest.TestCase):
    def test_complete_boundary(self):
        self.assertEqual(read_patch(lambda:"é".encode(),2),"é")
        self.assertEqual(read_patch(lambda:b"",0),"")
        for data,limit in [(b"abc",2),(b"\xff",10),(None,1),("x",1)]:
            with self.assertRaises(ValueError): read_patch(lambda:data,limit)
    def test_missing_and_bad_limits(self):
        def missing(): raise FileNotFoundError()
        with self.assertRaises(ValueError): read_patch(missing,10)
        for limit in [True,-1,2.0]:
            with self.assertRaises(ValueError): read_patch(lambda:b"a",limit)

if __name__=="__main__": unittest.main(verbosity=2)
