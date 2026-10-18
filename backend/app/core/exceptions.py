"""Application error hierarchy.

Every error that reaches the API layer is an `AppError` (or a subclass), so all
error responses share one envelope:

    { "detail": "Human readable message", "code": "machine_readable_code" }
"""


class AppError(Exception):
    def __init__(self, message: str, status_code: int = 400, code: str = "error") -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


class BadRequestError(AppError):
    def __init__(self, message: str = "Bad request") -> None:
        super().__init__(message, status_code=400, code="bad_request")


class NotFoundError(AppError):
    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__(message, status_code=404, code="not_found")


class ConflictError(AppError):
    def __init__(self, message: str = "Resource already exists") -> None:
        super().__init__(message, status_code=409, code="conflict")


class PayloadTooLargeError(AppError):
    def __init__(self, message: str = "Payload too large") -> None:
        super().__init__(message, status_code=413, code="payload_too_large")


class UnsupportedMediaTypeError(AppError):
    def __init__(self, message: str = "Unsupported media type") -> None:
        super().__init__(message, status_code=415, code="unsupported_media_type")


class AuthenticationError(AppError):
    def __init__(self, message: str = "Could not authenticate credentials") -> None:
        super().__init__(message, status_code=401, code="unauthenticated")


class AuthorizationError(AppError):
    def __init__(self, message: str = "Not enough permissions") -> None:
        super().__init__(message, status_code=403, code="forbidden")


class InvalidInputError(AppError):
    def __init__(self, message: str = "Invalid input") -> None:
        super().__init__(message, status_code=422, code="invalid_input")


class ServiceUnavailableError(AppError):
    def __init__(self, message: str = "Service temporarily unavailable") -> None:
        super().__init__(message, status_code=503, code="service_unavailable")


class QuotaExceededError(AppError):
    """A per-role quota, seat, or spend cap has been reached (HTTP 429)."""

    def __init__(self, message: str = "Quota exceeded") -> None:
        super().__init__(message, status_code=429, code="quota_exceeded")


class FeatureUnavailableError(AppError):
    """A feature that is valid but not configured on this deployment (HTTP 501)."""

    def __init__(self, message: str = "Feature not available") -> None:
        super().__init__(message, status_code=501, code="feature_unavailable")
