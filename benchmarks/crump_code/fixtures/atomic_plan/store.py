"""Minimal store protocol for the planning benchmark."""


class CounterStore:
    async def read_count(self, user_id: str) -> int:
        raise NotImplementedError

    async def write_count(self, user_id: str, value: int) -> None:
        raise NotImplementedError
