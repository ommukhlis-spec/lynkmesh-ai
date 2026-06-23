"""User model — core domain entity."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class UserRole(str, Enum):
    """User authorization roles."""

    ADMIN = "admin"
    MANAGER = "manager"
    USER = "user"
    GUEST = "guest"


class UserStatus(str, Enum):
    """User account status."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    PENDING_VERIFICATION = "pending_verification"


@dataclass
class User:
    """Core user entity."""

    id: str
    email: str
    username: str
    role: UserRole = UserRole.USER
    status: UserStatus = UserStatus.PENDING_VERIFICATION
    display_name: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_login: Optional[datetime] = None

    def is_active(self) -> bool:
        return self.status == UserStatus.ACTIVE

    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN

    def can_manage_users(self) -> bool:
        return self.role in (UserRole.ADMIN, UserRole.MANAGER)

    def activate(self) -> None:
        self.status = UserStatus.ACTIVE
        self.updated_at = datetime.now(timezone.utc)

    def suspend(self, reason: str = "") -> None:
        self.status = UserStatus.SUSPENDED
        self.updated_at = datetime.now(timezone.utc)

    def __repr__(self) -> str:
        return f"User(id={self.id!r}, email={self.email!r}, role={self.role.value})"
