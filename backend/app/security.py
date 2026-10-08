"""Password hashing and session token hashing."""

import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_hasher = PasswordHasher()
_DUMMY_HASH = _hasher.hash('not-a-real-password')
_INVITE_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'


def hash_password(password: str) -> str:
    """Hash a password with argon2id."""
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """Return whether the password matches the stored hash."""
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def dummy_verify(password: str) -> None:
    """Spend hash time when the login name does not exist."""
    verify_password(_DUMMY_HASH, password)


def new_session_token() -> str:
    """Return a new unguessable session token."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Return the SHA-256 hex digest used at rest."""
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def new_invite_code() -> str:
    """Return an 8-character code that is easy to read aloud."""
    return ''.join(secrets.choice(_INVITE_ALPHABET) for _ in range(8))
