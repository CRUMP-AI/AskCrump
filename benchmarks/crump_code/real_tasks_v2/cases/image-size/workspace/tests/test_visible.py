import unittest
import asyncio
from sizing import prepare
class Visible(unittest.TestCase):
    def test_no_upscale(self):
        self.assertEqual(prepare(10,20,100,10000,1,100),(10,20))
