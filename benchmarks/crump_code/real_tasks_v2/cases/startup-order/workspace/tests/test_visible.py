import unittest
import asyncio
from startup import Boot
class Visible(unittest.TestCase):
    def test_unarmed(self):
        calls=[]; Boot(False,lambda:calls.append(1),lambda:calls.append(2),lambda:calls.append(3))
        self.assertEqual(calls,[])
