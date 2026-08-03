from __future__ import annotations

from datetime import datetime, timedelta, timezone
import base64
import hashlib
import hmac
import re
import secrets
import uuid

try:
    import bcrypt
except ImportError:  # The standard-library fallback keeps local diagnostics usable.
    bcrypt = None


EMAIL_RE = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utcnow().isoformat()


def normalize_email(email: str) -> str:
    return email.strip().lower()


def validate_email(email: str) -> bool:
    return bool(EMAIL_RE.fullmatch(normalize_email(email)))


def validate_password(password: str) -> tuple[bool, str | None]:
    if len(password) < 10:
        return False, 'Password must be at least 10 characters long.'
    if len(password) > 256:
        return False, 'Password is too long.'
    if not re.search(r'[A-Za-z]', password) or not re.search(r'\d', password):
        return False, 'Password must contain at least one letter and one number.'
    return True, None


def _scrypt_hash(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    derived = hashlib.scrypt(password.encode('utf-8'), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"$scrypt$n=16384,r=8,p=1${base64.urlsafe_b64encode(salt).decode()}${base64.urlsafe_b64encode(derived).decode()}"


def hash_password(password: str) -> str:
    if bcrypt is not None:
        return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt(rounds=12)).decode('utf-8')
    return _scrypt_hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    if password_hash.startswith('$scrypt$'):
        try:
            _, _, params, salt_text, digest_text = password_hash.split('$', 4)
            values = dict(item.split('=', 1) for item in params.split(','))
            salt = base64.urlsafe_b64decode(salt_text.encode())
            expected = base64.urlsafe_b64decode(digest_text.encode())
            derived = hashlib.scrypt(
                password.encode('utf-8'),
                salt=salt,
                n=int(values['n']),
                r=int(values['r']),
                p=int(values['p']),
                dklen=len(expected),
            )
            return hmac.compare_digest(derived, expected)
        except (ValueError, TypeError, KeyError):
            return False
    if bcrypt is None:
        return False
    try:
        return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))
    except (ValueError, TypeError):
        return False


def random_token(byte_count: int = 48) -> str:
    return secrets.token_urlsafe(byte_count)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def safe_compare(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode('utf-8'), right.encode('utf-8'))


def new_uuid() -> str:
    return str(uuid.uuid4())


def expiry_iso(days: int = 0, hours: int = 0, minutes: int = 0) -> str:
    return (utcnow() + timedelta(days=days, hours=hours, minutes=minutes)).isoformat()


def normalize_chat_id(value: str | None) -> str:
    if value:
        try:
            return str(uuid.UUID(value))
        except (ValueError, TypeError):
            # Match migrations/001_python_backend.sql exactly so legacy IDs never duplicate.
            digest = hashlib.md5(f'askcrump:chat:{value}'.encode('utf-8')).hexdigest()
            return f'{digest[:8]}-{digest[8:12]}-5{digest[13:16]}-a{digest[17:20]}-{digest[20:32]}'
    return new_uuid()


def client_ip(headers: dict[str, str], fallback: str | None = None) -> str | None:
    forwarded = headers.get('x-forwarded-for')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return headers.get('x-real-ip') or fallback
