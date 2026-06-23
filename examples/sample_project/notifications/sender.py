"""
Notification sender — dispatches messages across channels.

Depends on:
- models.user (User)
- utils.validators (validate_email)
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Optional

from models.user import User
from utils.validators import validate_email

logger = logging.getLogger(__name__)


class NotificationChannel(str, Enum):
    EMAIL = "email"
    SMS = "sms"
    PUSH = "push"
    IN_APP = "in_app"


@dataclass
class Notification:
    """A notification message for a specific user."""

    user_id: str
    channel: NotificationChannel
    subject: str
    body: str
    template_id: str = ""
    metadata: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    sent_at: Optional[datetime] = None
    status: str = "pending"  # pending, sent, failed

    def mark_sent(self) -> None:
        self.sent_at = datetime.now(timezone.utc)
        self.status = "sent"

    def mark_failed(self, error: str) -> None:
        self.status = "failed"
        self.metadata["error"] = error


class NotificationSender:
    """
    Dispatches notifications across email, SMS, push, and in-app channels.

    Uses a pluggable transport architecture — real implementations
    would be injected at runtime (SMTP, Twilio, FCM, etc.).
    """

    def __init__(self) -> None:
        self._transports: dict[NotificationChannel, Callable[[Notification, User], bool]] = {}

    def register_transport(
        self,
        channel: NotificationChannel,
        handler: Callable[[Notification, User], bool],
    ) -> None:
        """
        Register a transport handler for a channel.

        Args:
            channel: The notification channel.
            handler: Callable that sends the notification and returns True on success.
        """
        self._transports[channel] = handler
        logger.info(f"Transport registered for channel: {channel.value}")

    def send(
        self,
        notification: Notification,
        user: User,
    ) -> bool:
        """
        Send a notification to a user.

        Args:
            notification: The notification to send.
            user: The recipient user.

        Returns:
            True if sent successfully, False otherwise.
        """
        handler = self._transports.get(notification.channel)
        if not handler:
            logger.error(f"No transport registered for channel: {notification.channel.value}")
            notification.mark_failed("No transport registered")
            return False

        # Pre-send validation
        if notification.channel == NotificationChannel.EMAIL:
            if not validate_email(user.email):
                notification.mark_failed("Invalid recipient email")
                return False

        try:
            success = handler(notification, user)
            if success:
                notification.mark_sent()
                logger.info(f"Notification sent: {notification.channel.value} → {user.id}")
            else:
                notification.mark_failed("Transport returned failure")
            return success
        except Exception as exc:
            notification.mark_failed(str(exc))
            logger.exception(f"Notification failed: {exc}")
            return False

    def send_bulk(
        self,
        notifications: list[tuple[Notification, User]],
    ) -> dict[str, bool]:
        """
        Send notifications to multiple users.

        Args:
            notifications: List of (Notification, User) tuples.

        Returns:
            Dict mapping notification IDs to success booleans.
        """
        results: dict[str, bool] = {}
        for notif, user in notifications:
            key = f"{notif.user_id}_{notif.channel.value}"
            results[key] = self.send(notif, user)
        return results

    def email_available(self) -> bool:
        """Check if an email transport is registered."""
        return NotificationChannel.EMAIL in self._transports

    def sms_available(self) -> bool:
        """Check if an SMS transport is registered."""
        return NotificationChannel.SMS in self._transports
