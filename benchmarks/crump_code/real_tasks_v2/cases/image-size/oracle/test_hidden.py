import sys
sys.path.insert(0,sys.argv.pop(1))
import unittest
import asyncio

from sizing import prepare
class Hidden(unittest.TestCase):
    def test_square_pixel_cap_and_portrait(self):
        self.assertEqual(prepare(4000,4000,4096,4_000_000,10,100),(2000,2000))
        self.assertEqual(prepare(1000,3000,2000,4_000_000,10,100),(666,2000))
        self.assertEqual(prepare(40,20,2000,4_000_000,10,100),(40,20))
    def test_bytes_boundary_and_dimensions(self):
        for args in [(10,10,20,400,100,100),(True,10,20,400,0,100),(0,10,20,400,0,100),(10,10,20,400,-1,100)]:
            with self.assertRaises(ValueError): prepare(*args)

if __name__=="__main__": unittest.main(verbosity=2)
