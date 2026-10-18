import sys
sys.path.insert(0,sys.argv.pop(1))
import unittest
import asyncio

from transport import request
class Hidden(unittest.IsolatedAsyncioTestCase):
    async def test_gateway_and_transport(self):
        items=[ConnectionError(),502,500,200]; seen=[]
        async def send():
            value=items.pop(0); seen.append(value)
            if isinstance(value,Exception): raise value
            return value
        self.assertEqual(await request(send,"get"),200)
        self.assertEqual(len(seen),4)
    async def test_writes_permanent_and_bound(self):
        for method,status,expected in [("POST",503,1),("GET",400,1),("HEAD",502,3)]:
            calls=[]
            async def send(): calls.append(1); return status
            self.assertEqual(await request(send,method,3),status)
            self.assertEqual(len(calls),expected)
    async def test_exhausted_connection(self):
        calls=[]
        async def send(): calls.append(1); raise ConnectionError("offline")
        with self.assertRaises(ConnectionError): await request(send,"GET",2)
        self.assertEqual(len(calls),2)

if __name__=="__main__": unittest.main(verbosity=2)
