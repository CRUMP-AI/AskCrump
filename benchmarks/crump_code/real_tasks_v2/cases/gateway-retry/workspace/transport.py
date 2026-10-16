async def request(send, method, max_attempts=4):
    for attempt in range(max_attempts):
        status = await send()
        if status not in {503,504} or attempt == max_attempts-1:
            return status
