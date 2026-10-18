from policy import retryable
async def process(task, run):
    try: await run(); return "completed"
    except TimeoutError: return "retrying" if retryable(task,"timeout") else "failed"
    except ConnectionError: return "retrying" if retryable(task,"network") else "failed"
    except Exception: return "failed"
