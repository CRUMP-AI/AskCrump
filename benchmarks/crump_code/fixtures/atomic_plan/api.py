"""Intentionally non-atomic request limiter used by the planning benchmark."""


async def allow_request(user_id: str, store, limit: int) -> bool:
    current = await store.read_count(user_id)
    if current >= limit:
        return False
    await store.write_count(user_id, current + 1)
    return True
