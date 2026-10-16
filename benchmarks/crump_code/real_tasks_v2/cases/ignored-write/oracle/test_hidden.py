import sys
sys.path.insert(0,sys.argv.pop(1))
import unittest
import asyncio

from writer import write
class Hidden(unittest.IsolatedAsyncioTestCase):
    async def test_zero_side_effects_for_rejection(self):
        for status,error in [(0,ValueError),(128,RuntimeError)]:
            calls=[]
            class FS:
                async def write(self,*args): calls.append("write")
                async def mkdir(self,*args): calls.append("mkdir")
            class Git:
                async def check_ignore(self,path): return status
            with self.assertRaises(error): await write(FS(),Git(),"gen/a.py","x")
            self.assertEqual(calls,[])
    async def test_eligible_parent_and_order(self):
        calls=[]
        class FS:
            async def write(self,*args): calls.append(("write",args))
            async def mkdir(self,*args): calls.append(("mkdir",args))
        class Git:
            async def check_ignore(self,path): calls.append(("check",path)); return 1
        self.assertEqual(await write(FS(),Git(),"src/a.py","x"),"src/a.py")
        self.assertEqual([c[0] for c in calls],["check","mkdir","write"])

if __name__=="__main__": unittest.main(verbosity=2)
