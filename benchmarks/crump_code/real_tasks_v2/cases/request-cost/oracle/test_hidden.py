import sys
sys.path.insert(0,sys.argv.pop(1))
import unittest
import asyncio

from budget import reserve
class Hidden(unittest.TestCase):
    def setUp(self):
        self.p={"model":"fixed","max_output":100,"max_bytes":1000,"input_rate":3,"output_rate":7,"call_limit":100}
        self.b={"model":"fixed","max_tokens":20,"messages":[],"system":"é"}
    def test_every_field_and_canonical_digest(self):
        first=reserve(self.b,self.p); self.assertGreater(first[2],4096)
        self.assertEqual(reserve(dict(reversed(list(self.b.items()))),self.p),first)
        self.assertNotEqual(reserve({**self.b,"tools":[{"name":"read"}]},self.p)[0],first[0])
        self.assertEqual(first[1],(first[2]*3+20*7+999999)//1000000)
    def test_rejections(self):
        for body in [{**self.b,"model":"other"},{**self.b,"max_tokens":True},{**self.b,"max_tokens":101},{**self.b,"x":float("nan")},{**self.b,"system":"a"*1001}]:
            with self.assertRaises(ValueError): reserve(body,self.p)
        with self.assertRaises(ValueError): reserve(self.b,{**self.p,"call_limit":0})

if __name__=="__main__": unittest.main(verbosity=2)
