from uuid import UUID

from backend.security import hash_password, normalize_chat_id, validate_password, verify_password


def test_password_round_trip_and_rejection():
    encoded = hash_password('CorrectHorse123')
    assert verify_password('CorrectHorse123', encoded)
    assert not verify_password('WrongHorse123', encoded)


def test_password_policy():
    assert validate_password('short1')[0] is False
    assert validate_password('longwithoutnumber')[0] is False
    assert validate_password('StrongEnough123')[0] is True


def test_legacy_chat_id_is_stable_uuid():
    first = normalize_chat_id('legacy-chat-42')
    second = normalize_chat_id('legacy-chat-42')
    assert first == second
    assert str(UUID(first)) == first


def test_uuid_chat_id_is_preserved():
    value = '7be94047-aaf4-458a-a599-8f37a0256e52'
    assert normalize_chat_id(value) == value
