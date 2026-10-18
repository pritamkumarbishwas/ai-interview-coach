"""Phase 9: field-level encryption of app-managed secrets."""

from app.core.crypto import PREFIX, FieldCipher


def test_roundtrip_with_a_fernet_key() -> None:
    cipher = FieldCipher("a-strong-passphrase")
    sealed = cipher.encrypt("super-secret")
    assert sealed.startswith(PREFIX)
    assert "super-secret" not in sealed
    assert cipher.decrypt(sealed) == "super-secret"


def test_encrypt_is_idempotent_and_blanks_pass_through() -> None:
    cipher = FieldCipher("a-strong-passphrase")
    sealed = cipher.encrypt("value")
    assert cipher.encrypt(sealed) == sealed  # never double-wraps
    assert cipher.encrypt("") == ""


def test_disabled_cipher_passes_values_through() -> None:
    cipher = FieldCipher(None)
    assert not cipher.enabled
    assert cipher.encrypt("plaintext") == "plaintext"
    # Legacy plaintext (no prefix) is returned unchanged even when enabled.
    assert FieldCipher("key").decrypt("legacy-plaintext") == "legacy-plaintext"


def test_wrong_or_missing_key_cannot_decrypt() -> None:
    sealed = FieldCipher("the-right-key").encrypt("value")
    assert FieldCipher("the-wrong-key").decrypt(sealed) == ""
    assert FieldCipher(None).decrypt(sealed) == ""
