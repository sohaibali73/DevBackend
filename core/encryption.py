"""
AES-256 encryption for sensitive data at rest.

Uses Fernet symmetric encryption (AES-128-CBC + HMAC-SHA256)
from the `cryptography` library for authenticated encryption.

API keys and other sensitive user data are encrypted before storage
and decrypted only when needed for API calls.
"""

import base64
import hashlib
import logging
from typing import Optional
from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

# Module-level cipher cache
_fernet: Optional[Fernet] = None


def _get_fernet() -> Fernet:
    """
    Get or create Fernet cipher from ENCRYPTION_KEY environment variable.
    
    Fernet requires a 32-byte URL-safe base64-encoded key (44 chars with padding).
    We derive a proper Fernet key from the ENCRYPTION_KEY using SHA-256.
    """
    global _fernet
    if _fernet is not None:
        return _fernet

    from config import get_settings
    settings = get_settings()

    raw_key = settings.encryption_key
    if not raw_key:
        raise RuntimeError(
            "ENCRYPTION_KEY is not set! Cannot encrypt/decrypt sensitive data. "
            "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
        )

    # Derive a proper 32-byte key using SHA-256, then base64-encode for Fernet
    derived = hashlib.sha256(raw_key.encode()).digest()
    fernet_key = base64.urlsafe_b64encode(derived)

    _fernet = Fernet(fernet_key)
    return _fernet


def encrypt_value(plaintext: str) -> str:
    """
    Encrypt a plaintext string and return base64-encoded ciphertext.
    
    Returns a string prefixed with 'enc:' to indicate encrypted data.
    This prefix allows us to distinguish encrypted vs legacy plain text values.
    
    Args:
        plaintext: The string to encrypt (e.g., an API key)
        
    Returns:
        String in format 'enc:<base64_ciphertext>'
    """
    if not plaintext or not plaintext.strip():
        return ""

    try:
        f = _get_fernet()
        encrypted = f.encrypt(plaintext.encode("utf-8"))
        return f"enc:{encrypted.decode('utf-8')}"
    except Exception as e:
        logger.error(f"Encryption failed: {e}")
        raise RuntimeError("Failed to encrypt value") from e


def decrypt_value(stored_value: str) -> str:
    """
    Decrypt an encrypted value back to plaintext.
    
    Handles:
    - Encrypted values (prefixed with 'enc:')
    - PostgreSQL bytea hex format ('\\x656e633a...' which is hex-encoded 'enc:...')
    - Legacy plain text values (no prefix) - returned as-is for backward compatibility
    
    Args:
        stored_value: The stored string (may be encrypted, hex-encoded, or plain text)
        
    Returns:
        Decrypted plaintext string
    """
    if not stored_value or not stored_value.strip():
        return ""

    # Handle PostgreSQL bytea hex format: \x656e633a... → enc:...
    # This happens when the column type is 'bytea' instead of 'text'
    if stored_value.startswith("\\x"):
        try:
            stored_value = bytes.fromhex(stored_value[2:]).decode("utf-8")
            logger.info(f"Decoded bytea hex to text: starts_with_enc={stored_value.startswith('enc:')}")
        except (ValueError, UnicodeDecodeError) as e:
            logger.error(f"Failed to decode bytea hex: {e}")

    # If not encrypted (legacy plain text), return as-is
    if not stored_value.startswith("enc:"):
        return stored_value

    try:
        f = _get_fernet()
        ciphertext = stored_value[4:]  # Remove 'enc:' prefix
        decrypted = f.decrypt(ciphertext.encode("utf-8"))
        return decrypted.decode("utf-8")
    except InvalidToken:
        logger.error("Decryption failed - invalid token. Key may have changed.")
        raise RuntimeError(
            "Failed to decrypt value. The ENCRYPTION_KEY may have changed. "
            "If you changed the key, existing encrypted data cannot be recovered."
        )
    except Exception as e:
        logger.error(f"Decryption failed: {e}")
        raise RuntimeError("Failed to decrypt value") from e


def is_encrypted(value: str) -> bool:
    """Check if a stored value is encrypted (has 'enc:' prefix)."""
    return bool(value) and value.startswith("enc:")
