"""Encrypt employee work-mailbox passwords at rest."""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


class MailCryptoError(Exception):
    """Raised when a mailbox secret cannot be encrypted or decrypted."""


def _fernet() -> Fernet:
    digest = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_mailbox_password(password: str) -> str:
    value = (password or "").strip()
    if not value:
        raise MailCryptoError("Mailbox password is empty.")
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_mailbox_password(token: str) -> str:
    raw = (token or "").strip()
    if not raw:
        raise MailCryptoError("No mailbox password is saved.")
    try:
        return _fernet().decrypt(raw.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, TypeError) as exc:
        raise MailCryptoError("Saved mailbox password could not be read.") from exc
