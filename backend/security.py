from __future__ import annotations

from datetime import datetime, timedelta, timezone
import base64
import hashlib
import hmac
import ipaddress
import re
import secrets
import uuid
from urllib.parse import urlparse

try:
    import bcrypt
except ImportError:  # The standard-library fallback keeps local diagnostics usable.
    bcrypt = None

try:
    from argon2 import PasswordHasher
    from argon2.exceptions import InvalidHashError, VerificationError
except ImportError:  # The standard-library fallback keeps local diagnostics usable.
    PasswordHasher = None
    InvalidHashError = VerificationError = ValueError


EMAIL_RE = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
ARGON2_HASHER = PasswordHasher() if PasswordHasher is not None else None

# Registration input is not proof that the submitter owns the inbox. Keep a
# deliberately unverifiable marker until the verification-link session (or a
# password-reset link) authorizes a fresh password. The database migration uses
# the same marker so old application instances remain fail closed during a
# schema-first rolling deployment.
PENDING_PASSWORD_HASH = '!pending-inbox-password-setup-v1!'


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
    if ARGON2_HASHER is not None:
        return ARGON2_HASHER.hash(password)
    return _scrypt_hash(password)


def password_hash_needs_upgrade(password_hash: str | None) -> bool:
    if not password_hash:
        return False
    if not password_hash.startswith('$argon2'):
        return True
    if ARGON2_HASHER is None:
        return False
    try:
        return ARGON2_HASHER.check_needs_rehash(password_hash)
    except (InvalidHashError, TypeError):
        return False


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    if password_hash.startswith('$argon2'):
        if ARGON2_HASHER is None:
            return False
        try:
            return ARGON2_HASHER.verify(password_hash, password)
        except (VerificationError, InvalidHashError, TypeError):
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
        # Legacy bcrypt hashes only contain the first 72 UTF-8 bytes. Slice the
        # candidate explicitly so existing long-password accounts remain usable
        # with bcrypt 5+, which rejects oversized input instead of truncating it.
        candidate = password.encode('utf-8')[:72]
        return bcrypt.checkpw(candidate, password_hash.encode('utf-8'))
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


def _header_value(headers: dict[str, str], name: str) -> str | None:
    value = headers.get(name)
    if value is not None:
        return value
    for key, candidate in headers.items():
        if key.lower() == name:
            return candidate
    return None


def _canonical_ip(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return str(ipaddress.ip_address(value.strip()))
    except ValueError:
        return None


def client_ip(headers: dict[str, str], fallback: str | None = None) -> str | None:
    """Best-effort client address, canonicalized.

    On Vercel, the ingress overwrites X-Forwarded-For itself and sets
    x-vercel-forwarded-for (documented behavior), so that header is the
    trustworthy source when present; other deployments fall back to the
    first X-Forwarded-For value, then x-real-ip. Values are parsed and
    re-serialized so equivalent addresses always key rate limits,
    sessions, and logs identically, and unparseable values never do.
    """
    for header in ('x-vercel-forwarded-for', 'x-forwarded-for', 'x-real-ip'):
        forwarded = _header_value(headers, header)
        if forwarded:
            candidate = _canonical_ip(forwarded.split(',')[0])
            if candidate:
                return candidate
    return _canonical_ip(fallback) or fallback


def origin_allowed(headers: dict[str, str], allowed_origins: tuple[str, ...] | list[str]) -> bool:
    """Same-site gate for cookie-minting endpoints.

    CORS alone does not stop a cross-site form POST from planting a
    session cookie, so state-creating public endpoints check the
    request's own metadata: Fetch Metadata cross-site is refused, and a
    present Origin must be same-host with the request or on the app's
    configured origin list. Requests with neither header (non-browser
    clients) are allowed; browsers always send at least one on POST.
    """
    fetch_site = (_header_value(headers, 'sec-fetch-site') or '').strip().lower()
    if fetch_site == 'cross-site':
        return False
    origin = (_header_value(headers, 'origin') or '').strip()
    if not origin:
        return True
    try:
        parsed = urlparse(origin)
    except ValueError:
        return False
    if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
        return False
    candidate = f'{parsed.scheme}://{parsed.netloc}'.lower()
    host = (_header_value(headers, 'host') or '').strip().lower()
    if host and parsed.netloc.lower() == host:
        return True
    return candidate in {entry.rstrip('/').lower() for entry in allowed_origins}
