import hashlib
import hmac
import json
def verify(value,key):
    try:
        if not isinstance(value,str) or len(value)>8192: raise ValueError("token")
        payload,signature=value.split(".")
        data=bytes.fromhex(payload); supplied=bytes.fromhex(signature)
        expected=hmac.new(key,data,hashlib.sha256).digest()
        if not hmac.compare_digest(supplied,expected): raise ValueError("signature")
        claims=json.loads(data)
        if not isinstance(claims,dict): raise ValueError("claims")
        return claims
    except (ValueError,TypeError,KeyError,UnicodeError) as exc: raise ValueError("identity") from exc
