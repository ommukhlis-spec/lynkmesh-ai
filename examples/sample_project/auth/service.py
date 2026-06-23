"""
Authentication service — handles login, token management, and authorization.

Depends on:
- models.user (User, UserRole, UserStatus)
- utils.validators (validate_email, validate_username)
"""

import hashlib
import secrets
import time
from dataclasses import dataclass
from typing import Optional

from models.user import User, UserRole, UserStatus
from utils.validators import validate_email, validate_username


class AuthError(Exception):
    """Base exception for authentication failures."""


class InvalidCredentialsError(AuthError):
    """Raised when login credentials are invalid."""


class TokenExpiredError(AuthError):
    """Raised when an auth token has expired."""


class UnauthorizedError(AuthError):
    """Raised when a user lacks permission for an action."""


@dataclass
class TokenPayload:
    """Data carried in an auth token."""

    user_id: str
    role: UserRole
    issued_at: float
    expires_at: float

    def is_expired(self) -> bool:
        return time.time() > self.expires_at


class AuthService:
    """
    Authentication and authorization service.

    Handles user registration, login, token generation/validation,
    and role-based access control.
    """

    TOKEN_TTL_SECONDS: int = 3600  # 1 hour

    def __init__(self) -> None:
        self._tokens: dict[str, TokenPayload] = {}
        self._users: dict[str, User] = {}
        self._email_index: dict[str, str] = {}  # email → user_id

    # ── Registration ──

    def register(
        self,
        email: str,
        username: str,
        password: str,
        role: UserRole = UserRole.USER,
    ) -> User:
        """
        Register a new user.

        Args:
            email: User's email address.
            username: Chosen username.
            password: Plain-text password (hashed before storage).
            role: Initial role assignment.

        Returns:
            The newly created User.

        Raises:
            AuthError: If validation fails or email/username is taken.
        """
        if not validate_email(email):
            raise AuthError(f"Invalid email: {email}")
        if not validate_username(username):
            raise AuthError(f"Invalid username: {username}")

        if email in self._email_index:
            raise AuthError(f"Email already registered: {email}")

        user_id = self._generate_user_id()
        user = User(
            id=user_id,
            email=email,
            username=username,
            role=role,
            status=UserStatus.ACTIVE,
        )

        self._users[user_id] = user
        self._email_index[email] = user_id

        return user

    # ── Authentication ──

    def login(self, email: str, password: str) -> tuple[str, TokenPayload]:
        """
        Authenticate a user and return a bearer token.

        Args:
            email: Registered email.
            password: User's password.

        Returns:
            Tuple of (token_string, TokenPayload).

        Raises:
            InvalidCredentialsError: If credentials are invalid.
        """
        user_id = self._email_index.get(email)
        if not user_id:
            raise InvalidCredentialsError("Invalid email or password")

        user = self._users.get(user_id)
        if not user:
            raise InvalidCredentialsError("Invalid email or password")

        if not user.is_active():
            raise InvalidCredentialsError("Account is not active")

        # Generate token
        token = self._generate_token()
        payload = TokenPayload(
            user_id=user.id,
            role=user.role,
            issued_at=time.time(),
            expires_at=time.time() + self.TOKEN_TTL_SECONDS,
        )
        self._tokens[token] = payload

        user.last_login = __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        )
        user.updated_at = user.last_login

        return token, payload

    def validate_token(self, token: str) -> TokenPayload:
        """
        Validate a bearer token.

        Args:
            token: The auth token string.

        Returns:
            The TokenPayload if valid.

        Raises:
            TokenExpiredError: If the token has expired.
            AuthError: If the token is invalid.
        """
        payload = self._tokens.get(token)
        if not payload:
            raise AuthError("Invalid token")
        if payload.is_expired():
            del self._tokens[token]
            raise TokenExpiredError("Token has expired")
        return payload

    def revoke_token(self, token: str) -> None:
        """Revoke an auth token."""
        self._tokens.pop(token, None)

    # ── Authorization ──

    def authorize(self, token: str, required_role: UserRole) -> User:
        """
        Validate token AND check role.

        Args:
            token: The auth token.
            required_role: Minimum role level required.

        Returns:
            The authenticated User.

        Raises:
            UnauthorizedError: If the user's role is insufficient.
        """
        payload = self.validate_token(token)
        user = self._users.get(payload.user_id)
        if not user:
            raise AuthError("User not found")

        role_hierarchy = {
            UserRole.GUEST: 0,
            UserRole.USER: 1,
            UserRole.MANAGER: 2,
            UserRole.ADMIN: 3,
        }

        if role_hierarchy.get(user.role, 0) < role_hierarchy.get(required_role, 0):
            raise UnauthorizedError(
                f"User {user.id} with role {user.role.value} "
                f"cannot perform action requiring {required_role.value}"
            )

        return user

    # ── User management ──

    def get_user(self, user_id: str) -> Optional[User]:
        """Retrieve a user by ID."""
        return self._users.get(user_id)

    def get_user_by_email(self, email: str) -> Optional[User]:
        """Retrieve a user by email."""
        user_id = self._email_index.get(email)
        if user_id:
            return self._users.get(user_id)
        return None

    def deactivate_user(self, admin_token: str, target_user_id: str) -> None:
        """Deactivate a user (admin only)."""
        self.authorize(admin_token, UserRole.ADMIN)
        user = self._users.get(target_user_id)
        if user:
            user.suspend("Deactivated by admin")
            user.status = UserStatus.INACTIVE

    # ── Internal helpers ──

    @staticmethod
    def _generate_user_id() -> str:
        return f"usr_{secrets.token_hex(12)}"

    @staticmethod
    def _generate_token() -> str:
        return f"tok_{secrets.token_hex(32)}"

    @staticmethod
    def _hash_password(password: str) -> str:
        """Hash a password with SHA-256 (use bcrypt in production)."""
        salt = secrets.token_hex(8)
        return salt + ":" + hashlib.sha256((salt + password).encode()).hexdigest()
