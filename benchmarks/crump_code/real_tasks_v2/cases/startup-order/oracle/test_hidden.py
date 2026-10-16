import sys
sys.path.insert(0,sys.argv.pop(1))
import unittest
import asyncio

from startup import Boot
class Hidden(unittest.TestCase):
    def test_ready_orders_and_once(self):
        for order in [("shell_ready","dom_ready"),("dom_ready","shell_ready")]:
            calls=[]; b=Boot(True,lambda:calls.append("install"),lambda:calls.append("enter"),lambda:calls.append("register"))
            self.assertEqual(calls,["install"])
            for event in (*order,*order): getattr(b,event)()
            self.assertEqual(calls,["install","enter","register"])
    def test_unarmed_and_dom_fallback(self):
        calls=[]; b=Boot(False,lambda:calls.append(1),lambda:calls.append(2),lambda:calls.append(3))
        b.shell_ready(); b.dom_ready(); self.assertEqual(calls,[])
        b=Boot(True,lambda:calls.append(1),lambda:calls.append(2),lambda:calls.append(3)); b.dom_ready()
        self.assertEqual(calls,[1,2,3])

if __name__=="__main__": unittest.main(verbosity=2)
