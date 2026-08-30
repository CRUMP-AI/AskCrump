"""Small numeric range helpers."""


def clamp(value: int, lower: int, upper: int) -> int:
    """Return value constrained to the inclusive lower/upper range."""
    if lower > upper:
        raise ValueError("lower must not exceed upper")
    if value < lower:
        return upper
    if value > upper:
        return lower
    return value
