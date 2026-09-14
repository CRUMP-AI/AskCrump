from uuid import UUID

import bcrypt

from backend.security import (
    hash_password,
    normalize_chat_id,
    password_hash_needs_upgrade,
    validate_password,
    verify_password,
)


def test_password_round_trip_and_rejection():
    encoded = hash_password('CorrectHorse123')
    assert encoded.startswith('$argon2id$')
    assert verify_password('CorrectHorse123', encoded)
    assert not verify_password('WrongHorse123', encoded)
    assert password_hash_needs_upgrade(encoded) is False


def test_long_password_uses_every_utf8_byte():
    shared_prefix = 'A1' + ('x' * 70)
    encoded = hash_password(shared_prefix + 'first ending')
    assert verify_password(shared_prefix + 'first ending', encoded)
    assert not verify_password(shared_prefix + 'other ending', encoded)


def test_legacy_bcrypt_long_password_remains_compatible_and_needs_upgrade():
    password = 'A1' + ('x' * 80) + 'one'
    legacy_hash = bcrypt.hashpw(password.encode('utf-8')[:72], bcrypt.gensalt(rounds=4)).decode()
    assert verify_password(password, legacy_hash)
    assert password_hash_needs_upgrade(legacy_hash)


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
