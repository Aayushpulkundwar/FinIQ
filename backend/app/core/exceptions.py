from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from loguru import logger


# Custom Application Exceptions
class AppException(Exception):
    """Base exception for FinsightAI application."""
    def __init__(self, message: str, status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class NotFoundException(AppException):
    """Raised when a resource is not found."""
    def __init__(self, message: str = "Resource not found"):
        super().__init__(message, status_code=status.HTTP_404_NOT_FOUND)


class BadRequestException(AppException):
    """Raised for invalid operations."""
    def __init__(self, message: str = "Bad request"):
        super().__init__(message, status_code=status.HTTP_400_BAD_REQUEST)


class AuthenticationException(AppException):
    """Raised for authentication failures."""
    def __init__(self, message: str = "Could not authenticate user"):
        super().__init__(message, status_code=status.HTTP_401_UNAUTHORIZED)


class AuthorizationException(AppException):
    """Raised for permissions or roles failure."""
    def __init__(self, message: str = "Not authorized"):
        super().__init__(message, status_code=status.HTTP_403_FORBIDDEN)


class DatabaseException(AppException):
    """Raised for database errors."""
    def __init__(self, message: str = "Database transaction failed"):
        super().__init__(message, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AIOrchestrationException(AppException):
    """Raised when the AI or RAG pipeline fails."""
    def __init__(self, message: str = "AI reasoning or retrieval failed"):
        super().__init__(message, status_code=status.HTTP_502_BAD_GATEWAY)


# Exception handlers registration
def setup_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
        logger.error(f"Application error on {request.url.path}: {exc.message}")
        return JSONResponse(
            status_code=exc.status_code,
            content={"success": False, "detail": exc.message},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = exc.errors()
        logger.warning(f"Validation error on {request.url.path}: {errors}")
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "success": False,
                "detail": "Validation error",
                "errors": errors,
            },
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(f"Unhandled system exception occurred on {request.url.path}: {str(exc)}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "success": False,
                "detail": "Internal server error occurred.",
            },
        )
