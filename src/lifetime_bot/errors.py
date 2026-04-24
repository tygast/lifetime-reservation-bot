"""Shared exception types for the Life Time bot."""


class LifetimeAPIError(Exception):
    """Raised when a Life Time API call returns an unexpected response."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code

    @property
    def is_retryable(self) -> bool:
        return self.status_code is not None and self.status_code >= 500
