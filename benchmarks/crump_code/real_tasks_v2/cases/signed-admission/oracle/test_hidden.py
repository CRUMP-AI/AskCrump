import sys
sys.path.insert(0,sys.argv.pop(1))
import unittest
import asyncio

import hashlib,hmac,json
from admission import admit
class Hidden(unittest.IsolatedAsyncioTestCase):
    async def test_valid_projection(self):
        policy={k:k+"-expected" for k in ("issuer","audience","project","team","environment")}; seen=[]
        async def provision(value): seen.append(value); return "ok"
        claims={**policy,"exp":101,"untrusted":"extra"}; data=json.dumps(claims).encode(); key=b"public-fixture-key"
        value=data.hex()+"."+hmac.new(key,data,hashlib.sha256).hexdigest()
        self.assertEqual(await admit(value,key,policy,100,provision),"ok")
        self.assertEqual(seen,[{k:policy[k] for k in ("project","team")}])
    async def test_signature_and_each_binding(self):
        policy={k:k for k in ("issuer","audience","project","team","environment")}; key=b"public-fixture-key"
        async def provision(value): self.fail("invalid identity provisioned")
        for change in [{"exp":100},{"exp":True},*({k:"wrong"} for k in policy),{"forge":True}]:
            claims={**policy,"exp":200,**change}; data=json.dumps(claims).encode()
            signature=hmac.new(b"wrong" if change.get("forge") else key,data,hashlib.sha256).hexdigest()
            with self.assertRaises(ValueError): await admit(data.hex()+"."+signature,key,policy,100,provision)

if __name__=="__main__": unittest.main(verbosity=2)
