import json
def verify(value,key): return json.loads(bytes.fromhex(value.split(".")[0]))
