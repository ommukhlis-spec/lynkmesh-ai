"""Input validation utilities."""

import re
from typing import Optional

# Email regex — pragmatic, not RFC 5321 exhaustive
_EMAIL_PATTERN = re.compile(
    r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?"
    r"(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$"
)

_USERNAME_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]{2,31}$")


def validate_email(email: str) -> bool:
    """
    Validate an email address.

    Args:
        email: The email address to validate.

    Returns:
        True if the email is valid, False otherwise.
    """
    if not email or not isinstance(email, str):
        return False
    if len(email) > 254:
        return False
    return bool(_EMAIL_PATTERN.match(email))


def validate_username(username: str) -> bool:
    """
    Validate a username.

    Rules:
    - 3-32 characters
    - Starts with a letter
    - Contains only alphanumeric and underscores

    Args:
        username: The username to validate.

    Returns:
        True if valid, False otherwise.
    """
    if not username or not isinstance(username, str):
        return False
    return bool(_USERNAME_PATTERN.match(username))


def sanitize_input(value: str, max_length: int = 1024) -> str:
    """
    Sanitize a user-provided string.

    Args:
        value: The input string.
        max_length: Maximum allowed length.

    Returns:
        Sanitized string.
    """
    if not value:
        return ""
    # Strip leading/trailing whitespace
    sanitized = value.strip()
    # Truncate to max length
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length]
    return sanitized


def is_valid_password(password: str) -> tuple[bool, Optional[str]]:
    """
    Validate a password against strength requirements.

    Args:
        password: The password to validate.

    Returns:
        Tuple of (is_valid, error_message).
    """
    if len(password) < 8:
        return False, "Password must be at least 8 characters"
    if len(password) > 128:
        return False, "Password must not exceed 128 characters"
    if not re.search(r"[A-Z]", password):
        return False, "Password must contain at least one uppercase letter"
    if not re.search(r"[a-z]", password):
        return False, "Password must contain at least one lowercase letter"
    if not re.search(r"\d", password):
        return False, "Password must contain at least one digit"
    return True, None
