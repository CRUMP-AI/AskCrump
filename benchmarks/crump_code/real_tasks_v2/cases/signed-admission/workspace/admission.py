from tokens import verify
async def admit(value,key,policy,now,provision):
    claims=verify(value,key)
    if claims["exp"]<now: raise ValueError("expired")
    return await provision(claims)
