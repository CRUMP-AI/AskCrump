from backend.credits_catalog import by_code, by_native_product, packs


def test_credit_catalog_is_stable():
    values = packs()
    assert [item.credits for item in values] == [50, 150, 400]
    assert len({item.code for item in values}) == 3
    assert len({item.native_product_id for item in values}) == 3


def test_credit_catalog_lookup():
    assert by_code('credits_150').credits == 150
    assert by_native_product('askcrump_credits_400').credits == 400
    assert by_code('nope') is None
