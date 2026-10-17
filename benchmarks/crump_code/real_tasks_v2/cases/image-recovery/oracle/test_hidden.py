import sys
sys.path.insert(0,sys.argv.pop(1))
import unittest
import asyncio

from copy import deepcopy
from recovery import sanitize
class Hidden(unittest.TestCase):
    def test_legacy_recovery_detached_whitelist(self):
        item={"role":"user","content":"edit","replyErrorCode":"INVALID_IMAGE_EDIT_SOURCE","replyRecovery":{"action":"revise_image_request","usageRestored":True,"extra":"no"},"approved":True}
        original=deepcopy(item); result=sanitize(item)
        self.assertEqual(result["replyRecovery"]["changeRequired"],"reference")
        self.assertNotIn("approved",result); self.assertNotIn("extra",result["replyRecovery"])
        result["replyRecovery"]["usageRestored"]=False; self.assertEqual(item,original)
    def test_reject_bad_role_code_type_and_change(self):
        base={"role":"user","content":"x","replyErrorCode":"IMAGE_SAFETY_REJECTED","replyRecovery":{"action":"revise_image_request","usageRestored":True}}
        for change in [{"role":"assistant"},{"replyErrorCode":"UNKNOWN"},{"replyRecovery":{"action":"revise_image_request","usageRestored":1}},{"replyRecovery":{"action":"revise_image_request","usageRestored":True,"changeRequired":"reference"}}]:
            self.assertNotIn("replyRecovery",sanitize({**base,**change}))

if __name__=="__main__": unittest.main(verbosity=2)
