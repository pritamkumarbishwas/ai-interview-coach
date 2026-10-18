"""Application-level encryption for secrets at rest (Phase 9).

Only *reversible* secrets are handled here — values the app must read back, such
as the ATS webhook signing secret. One-way values (password hashes, magic-link
token hashes) are already safe at rest and are not touched.

The cipher wraps ``cryptography``'s Fernet (AES-128-CBC + HMAC). The key comes
from ``FIELD_ENCRYPTION_KEY``; either a real Fernet key or an arbitrary
passphrase (stretched with SHA-256) is accepted. When no key is configured the
cipher is disabled and values pass through unchanged, which keeps local
development and existing deployments working.
"""

import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

logger = logging.getLogger(__name__)

# Marks a stored value as ciphertext so legacy plaintext keeps working and
# re-encryption is idempotent.
PREFIX = "enc:v1:"


def _derive_key(raw: str | None) -> bytes | None:
    if not raw or not raw.strip():
        return None
    value = raw.strip()
    try:
        # A valid Fernet key is 32 urlsafe-base64 bytes.
        decoded = base64.urlsafe_b64decode(value)
        if len(decoded) == 32:
            return value.encode()
    except Exception:
        pass
    return base64.urlsafe_b64encode(hashlib.sha256(value.encode()).digest())


class FieldCipher:
    def __init__(self, key: str | None) -> None:
        derived = _derive_key(key)
        self._fernet = Fernet(derived) if derived else None
        if self._fernet is None:
            logger.warning(
                "FIELD_ENCRYPTION_KEY is not set; secrets are stored unencrypted."
            )

    @property
    def enabled(self) -> bool:
        return self._fernet is not None

    def encrypt(self, value: str) -> str:
        """Encrypt a value, leaving empty strings and ciphertext untouched."""
        if not value or value.startswith(PREFIX) or self._fernet is None:
            return value
        token = self._fernet.encrypt(value.encode()).decode()
        return f"{PREFIX}{token}"

    def decrypt(self, value: str) -> str:
        """Decrypt a value; plaintext (legacy) is returned unchanged."""
        if not value or not value.startswith(PREFIX):
            return value
        if self._fernet is None:
            logger.error(
                "Cannot decrypt a stored secret: FIELD_ENCRYPTION_KEY is missing."
            )
            return ""
        try:
            return self._fernet.decrypt(value[len(PREFIX) :].encode()).decode()
        except InvalidToken:
            logger.error("Stored secret could not be decrypted (wrong key?).")
            return ""


field_cipher = FieldCipher(settings.field_encryption_key)
