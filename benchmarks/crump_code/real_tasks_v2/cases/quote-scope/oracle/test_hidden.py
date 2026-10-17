import sys
sys.path.insert(0,sys.argv.pop(1))
import unittest
import asyncio

from scope import digest
from dispatch import authorized
class Hidden(unittest.IsolatedAsyncioTestCase):
    async def test_valid_canonical_receipt(self):
        task={"owner":"u","id":"a","mode":"plan"}; receipt={"id":"ledger","credits":12}; calls=[]
        async def charge(n): calls.append(n); return receipt
        self.assertIs(await authorized(task,{"scope":digest(dict(reversed(list(task.items())))),"credits":12},charge),receipt)
        self.assertEqual(calls,[12])
    async def test_changed_scope_has_zero_charge(self):
        task={"owner":"u","id":"a","mode":"plan"}; calls=[]
        async def charge(n): calls.append(n)
        confirmation={"scope":digest(task),"credits":12}
        for field,value in [("owner","v"),("id","b"),("mode","implement")]:
            with self.assertRaises(ValueError): await authorized({**task,field:value},confirmation,charge)
        self.assertEqual(calls,[])
    async def test_invalid_credit_types(self):
        task={"owner":"u","id":"a","mode":"plan"}
        async def charge(n): self.fail("invalid amount charged")
        for n in [True,12.0,"12",0,11,13]:
            with self.assertRaises(ValueError): await authorized(task,{"scope":digest(task),"credits":n},charge)

if __name__=="__main__": unittest.main(verbosity=2)
