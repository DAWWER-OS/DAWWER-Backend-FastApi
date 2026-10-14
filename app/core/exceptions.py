from typing import Any
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from app.core.logging import logger
from app.schemas.response import ErrorResponseModel


def http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    if isinstance(exc.detail, str):
        message = exc.detail
        detail_val = exc.detail
        code = f"HTTP_{exc.status_code}"
        content = {
            "success": False,
            "error_code": code,
            "code": code,
            "message": message,
            "detail": detail_val,
        }
    elif isinstance(exc.detail, dict):
        message = str(exc.detail.get("message") or exc.detail.get("detail") or "Request error occurred")
        detail_val = exc.detail.get("detail") or exc.detail.get("message") or "Request error occurred"
        code = str(exc.detail.get("code") or exc.detail.get("error_code") or f"HTTP_{exc.status_code}")
        content = {
            "success": False,
            "error_code": code,
            "code": code,
            "message": message,
            "detail": detail_val,
            "details": exc.detail,
        }
        for k, v in exc.detail.items():
            content[k] = v
    else:
        message = "Request error occurred"
        content = {
            "success": False,
            "error_code": f"HTTP_{exc.status_code}",
            "code": f"HTTP_{exc.status_code}",
            "message": message,
            "detail": exc.detail,
            "details": exc.detail,
        }

    headers = dict(exc.headers or {})
    media_type = "application/problem+json" if ("type" in content or "title" in content) else "application/json"
    return JSONResponse(
        status_code=exc.status_code,
        content=content,
        headers=headers,
        media_type=media_type,
    )


def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    formatted_errors = []
    for err in exc.errors():
        field_path = " -> ".join(str(loc) for loc in err.get("loc", []))
        formatted_errors.append(
            {
                "field": field_path,
                "message": err.get("msg"),
                "type": err.get("type"),
            }
        )

    error_body = ErrorResponseModel(
        success=False,
        error_code="VALIDATION_ERROR",
        message="Request input validation failed",
        details=formatted_errors,
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=error_body.model_dump(),
    )


def unhandled_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    logger.error(f"Unhandled server exception: {exc}", exc_info=True)

    error_body = ErrorResponseModel(
        success=False,
        error_code="INTERNAL_SERVER_ERROR",
        message="An unexpected server error occurred",
        details=None,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_body.model_dump(),
    )


class AIQuotaExceededException(Exception):
    """Raised when a store has exhausted its AI scan quota."""

    def __init__(
        self,
        message: str = "The store has reached its AI scan quota.",
        scans_used: int = 30,
        scans_limit: int = 30,
        resets_in_days: int = 0,
        alternative: str = "EXCEL_BULK_IMPORT",
    ) -> None:
        self.message = message
        self.scans_used = scans_used
        self.scans_limit = scans_limit
        self.resets_in_days = max(0, int(resets_in_days))
        self.alternative = alternative
        super().__init__(self.message)


def ai_quota_exceeded_handler(
    request: Request,
    exc: AIQuotaExceededException,
) -> JSONResponse:
    """Returns flat JSON response for AI quota exceeded according to specification."""
    content = {
        "code": "AI_QUOTA_EXCEEDED",
        "message": exc.message,
        "scans_used": exc.scans_used,
        "scans_limit": exc.scans_limit,
        "resets_in_days": exc.resets_in_days,
        "alternative": exc.alternative,
    }
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content=content,
    )


def setup_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AIQuotaExceededException, ai_quota_exceeded_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
