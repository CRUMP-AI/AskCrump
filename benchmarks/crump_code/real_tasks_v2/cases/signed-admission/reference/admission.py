from tokens import verify
async def admit(value,key,policy,now,provision):
    claims=verify(value,key)
    if type(claims.get("exp")) is not int or claims["exp"]<=now: raise ValueError("expired")
    if any(claims.get(name)!=policy[name] for name in ("issuer","audience","project","team","environment")): raise ValueError("binding")
    return await provision({name:policy[name] for name in ("project","team")})
