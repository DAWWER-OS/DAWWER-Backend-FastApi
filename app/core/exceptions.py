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
        details = None
    elif isinstance(exc.detail, dict):
        message = str(exc.detail.get("message", "Request error occurred"))
        details = exc.detail
    else:
        message = "Request error occurred"
        details = exc.detail

    error_body = ErrorResponseModel(
        success=False,
        error_code=f"HTTP_{exc.status_code}",
        message=message,
        details=details,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body.model_dump(),
        headers=exc.headers,
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


def setup_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
