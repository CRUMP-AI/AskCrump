import unittest
import asyncio
from tokens import verify
class Visible(unittest.TestCase):
    def test_invalid(self):
        with self.assertRaises(ValueError): verify("broken",b"public-key")
