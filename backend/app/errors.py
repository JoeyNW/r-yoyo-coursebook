"""Application errors returned as JSON."""


class AppError(Exception):
    """A request failed with a stable error code."""

    def __init__(
        self,
        code: str,
        message: str,
        status: int,
        extra: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.extra = extra or {}
