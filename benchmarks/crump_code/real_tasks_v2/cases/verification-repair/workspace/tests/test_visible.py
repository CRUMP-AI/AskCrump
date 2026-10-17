import unittest
import asyncio
from workspace import Workspace
class Visible(unittest.TestCase):
    def test_edit_generation(self):
        w=Workspace(); w.edit(); self.assertEqual(w.generation,1)
