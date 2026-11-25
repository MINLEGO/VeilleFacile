"""Domain errors; the app maps them to HTTP (see app.py)."""


class UpstreamError(Exception):
    """LLM / embedding / fetch failure or timeout -> 502."""


class QuotaError(Exception):
    """Provider quota exhausted -> 503 + Retry-After."""

    def __init__(self, retry_after: int = 60):
        super().__init__("quota exhausted")
        self.retry_after = retry_after


class CaptureRequired(Exception):
    """No full_text and the site cannot be fetched -> 422."""
