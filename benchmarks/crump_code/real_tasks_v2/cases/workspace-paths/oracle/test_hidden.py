import sys
sys.path.insert(0,sys.argv.pop(1))
import unittest
import asyncio

from paths import normalize
class Hidden(unittest.TestCase):
    def test_canonical(self):
        for path in ["src/a.py","docs/a b.md","a..b.txt"]: self.assertEqual(normalize(path),path)
    def test_escapes_and_protected(self):
        for path in ["/a.py","a//b.py","a/./b.py","a/../b.py","C:/a.py","a\\b.py",".GIT/x.py","x/.env/a.py"," a.py","a.py ","a\n.py",None,"img.png"]:
            with self.assertRaises(ValueError,msg=repr(path)): normalize(path)

if __name__=="__main__": unittest.main(verbosity=2)
