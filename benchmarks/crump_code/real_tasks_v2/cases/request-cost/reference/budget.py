import hashlib,json
def reserve(body,policy):
    try:
        if not isinstance(body,dict) or body.get("model")!=policy["model"]: raise ValueError("model")
        for field in ("max_output","max_bytes","input_rate","output_rate","call_limit"):
            if type(policy[field]) is not int or policy[field]<=0: raise ValueError("policy")
        output=body.get("max_tokens")
        if type(output) is not int or not 1<=output<=policy["max_output"]: raise ValueError("output")
        data=json.dumps(body,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()
        if len(data)>policy["max_bytes"]: raise ValueError("bytes")
        ceiling=len(data)+4096
        cost=(ceiling*policy["input_rate"]+output*policy["output_rate"]+999999)//1000000
        if cost>policy["call_limit"]: raise ValueError("budget")
        return hashlib.sha256(data).hexdigest(),cost,ceiling
    except (TypeError,KeyError,UnicodeError) as exc: raise ValueError("request") from exc
