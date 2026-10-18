import asyncio
async def request(send, method, max_attempts=4):
    allowed = method.upper() in {"GET", "HEAD"}
    for attempt in range(max(1, max_attempts)):
        try:
            status = await send()
        except ConnectionError:
            if not allowed or attempt == max(1,max_attempts)-1:
                raise
        else:
            if not allowed or status not in {408,500,502,503,504,520} or attempt == max(1,max_attempts)-1:
                return status
        await asyncio.sleep(0)
