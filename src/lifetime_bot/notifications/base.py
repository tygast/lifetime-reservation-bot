"""Base notification service interface."""

from __future__ import annotations

from abc import ABC, abstractmethod


class NotificationService(ABC):
    """Abstract base class for notification services."""

    @abstractmethod
    def send(self, subject: str, message: str) -> bool:
        """Send a notification.

        Args:
            subject: The notification subject/title.
            message: The notification body/content.

        Returns:
            True if the notification was sent successfully, False otherwise.
        """

    @abstractmethod
    def is_configured(self) -> bool:
        """Check if the notification service is properly configured.

        Returns:
            True if the service is configured and ready to send notifications.
        """
