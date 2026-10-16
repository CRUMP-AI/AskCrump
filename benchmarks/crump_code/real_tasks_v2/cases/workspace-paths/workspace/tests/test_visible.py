import unittest
import asyncio
from paths import normalize
class Visible(unittest.TestCase):
    def test_source(self):
        self.assertEqual(normalize("src/a.py"),"src/a.py")
