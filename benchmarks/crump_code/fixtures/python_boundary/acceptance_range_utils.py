from benchmarks.crump_code.fixtures.python_boundary.range_utils import clamp


def test_clamp_preserves_values_inside_the_range():
    assert clamp(4, 1, 9) == 4


def test_clamp_uses_the_nearest_boundary():
    assert clamp(-2, 1, 9) == 1
    assert clamp(14, 1, 9) == 9


def test_clamp_rejects_an_inverted_range():
    try:
        clamp(4, 9, 1)
    except ValueError:
        return
    raise AssertionError("clamp must reject lower values above upper values")
