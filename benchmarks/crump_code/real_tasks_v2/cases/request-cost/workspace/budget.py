import hashlib,json
def reserve(body,policy):
    data=json.dumps(body.get("messages",[])).encode()
    cost=(len(data)*policy["input_rate"]+body["max_tokens"]*policy["output_rate"])//1000000
    return hashlib.sha256(data).hexdigest(),cost,len(data)
