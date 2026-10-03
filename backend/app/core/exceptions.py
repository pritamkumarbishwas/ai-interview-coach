class AppError(Exception):
    def __init__(self, message: str, status_code: int = 400, code: str = "error") -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


class NotFoundError(AppError):
    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__(message, status_code=404, code="not_found")


class ConflictError(AppError):
    def __init__(self, message: str = "Resource already exists") -> None:
        super().__init__(message, status_code=409, code="conflict")


class AuthenticationError(AppError):
    def __init__(self, message: str = "Could not authenticate credentials") -> None:
        super().__init__(message, status_code=401, code="unauthenticated")


class AuthorizationError(AppError):
    def __init__(self, message: str = "Not enough permissions") -> None:
        super().__init__(message, status_code=403, code="forbidden")


class InvalidInputError(AppError):
    def __init__(self, message: str = "Invalid input") -> None:
        super().__init__(message, status_code=422, code="invalid_input")
