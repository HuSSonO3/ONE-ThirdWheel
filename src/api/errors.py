"""Every error response has the contract's `Error` shape: {code, message, details?}."""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.status, self.code, self.message, self.details = status, code, message, details


def unauthenticated(message: str = "Not logged in.") -> ApiError:
    return ApiError(401, "unauthenticated", message)


def forbidden(message: str = "You don't have access to this.", code: str = "forbidden") -> ApiError:
    return ApiError(403, code, message)


def not_found(what: str = "Resource") -> ApiError:
    return ApiError(404, "not_found", f"{what} not found.")


def conflict(code: str, message: str) -> ApiError:
    return ApiError(409, code, message)


def invalid(field: str, message: str) -> ApiError:
    return ApiError(422, "validation_error", message, {field: message})


def _body(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"code": code, "message": message}
    if details:
        body["details"] = details
    return body


HTTP_CODES = {400: "bad_request", 401: "unauthenticated", 403: "forbidden", 404: "not_found",
              405: "method_not_allowed", 409: "conflict", 413: "too_large", 422: "validation_error"}


def install(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(_body(exc.code, exc.message, exc.details), status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = {".".join(str(p) for p in e["loc"]): e["msg"] for e in exc.errors()}
        return JSONResponse(_body("validation_error", "The request is invalid.", details), status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = HTTP_CODES.get(exc.status_code, "error")
        return JSONResponse(_body(code, str(exc.detail)), status_code=exc.status_code, headers=exc.headers)
