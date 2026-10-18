import sys
sys.path.insert(0,sys.argv.pop(1))
import unittest
import asyncio

from merge import merge
from view import activity
class Hidden(unittest.TestCase):
    def test_latest_and_detached(self):
        a = {"id":"a", "stamp":1,"status":"running","detail":{"n":1}}
        b = {"id":"a", "stamp":3,"status":"completed","detail":{"n":2}}
        result = merge([a],[b])
        self.assertEqual(result[0]["status"],"completed")
        result[0]["detail"]["n"] = 90
        self.assertEqual(b["detail"]["n"],2)
    def test_tie_uses_later_read(self):
        self.assertEqual(merge([{"id":"x","stamp":4,"status":"running"}],
          [{"id":"x","stamp":4,"status":"failed"}])[0]["status"],"failed")
    def test_group_limit_and_drafts(self):
        rows = [{"id":"done","stamp":9,"status":"completed"},
          {"id":"draft","stamp":10,"status":"queued"},
          {"id":"live","stamp":2,"status":"running"},
          {"id":"paid","stamp":3,"status":"queued","paid":True},
          {"stamp":30,"status":"running"}]
        self.assertEqual([r["id"] for r in activity([rows],2)],["paid","live"])
        self.assertEqual(activity([rows],0),[])

if __name__=="__main__": unittest.main(verbosity=2)
