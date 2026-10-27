from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.app.schemas.common import ApiErrorOut


API_ERROR_RESPONSES = {
    400: {"model": ApiErrorOut, "description": "The request is invalid."},
    404: {"model": ApiErrorOut, "description": "The requested resource does not exist."},
    409: {"model": ApiErrorOut, "description": "The resource changed or conflicts with current state."},
    413: {"model": ApiErrorOut, "description": "The request payload is too large."},
    422: {"model": ApiErrorOut, "description": "The request does not match the API schema."},
    428: {"model": ApiErrorOut, "description": "A current resource version is required."},
    500: {"model": ApiErrorOut, "description": "The request could not be completed."},
}

_STATUS_DEFAULTS = {
    400: ("invalid_request", "检查请求字段后重试。"),
    404: ("not_found", "重新读取资源目录并确认资源身份。"),
    409: ("conflict", "重新读取当前状态并协调后重试。"),
    413: ("payload_too_large", "缩小内容或附件后重试。"),
    422: ("validation_error", "按返回的字段错误修正请求。"),
    428: ("precondition_required", "先读取资源详情，再使用返回的版本发起写入。"),
    429: ("rate_limited", "稍后重试。"),
    500: ("internal_error", "保留请求信息并稍后重试。"),
}


def _error_payload(
    status_code: int,
    *,
    message: str,
    code: str | None = None,
    next_action: str | None = None,
    details: Any = None,
) -> dict[str, Any]:
    default_code, default_action = _STATUS_DEFAULTS.get(
        status_code, ("request_failed", "检查服务状态后重试。")
    )
    return {
        "error": {
            "code": code or default_code,
            "message": message,
            "nextAction": next_action or default_action,
            "details": details,
        }
    }


def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    detail = exc.detail
    if isinstance(detail, dict):
        payload = _error_payload(
            exc.status_code,
            message=str(detail.get("message") or "请求失败。"),
            code=str(detail.get("code") or "") or None,
            next_action=str(detail.get("nextAction") or "") or None,
            details=detail.get("details"),
        )
    else:
        payload = _error_payload(exc.status_code, message=str(detail))
    return JSONResponse(
        status_code=exc.status_code,
        content=payload,
        headers=exc.headers,
    )


async def _validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
    details = [
        {
            "field": ".".join(str(part) for part in error.get("loc", ()) if part != "body"),
            "message": error.get("msg", "Invalid value"),
            "rule": error.get("type", "value_error"),
        }
        for error in exc.errors()
    ]
    missing_if_match = any(
        error.get("type") == "missing"
        and error.get("loc", ())[0:1] == ("header",)
        and any(str(part).lower() == "if-match" for part in error.get("loc", ())[1:])
        for error in exc.errors()
    )
    if missing_if_match and len(details) == 1:
        return JSONResponse(
            status_code=428,
            content=_error_payload(
                428,
                code="precondition_required",
                message="笔记写入需要 If-Match 版本条件。",
                next_action="先读取笔记详情，并将 updatedAt 原样放入 If-Match 请求头。",
                details=details,
            ),
        )
    return JSONResponse(
        status_code=422,
        content=_error_payload(
            422,
            code="validation_error",
            message="请求内容与 API schema 不匹配。",
            details=details,
        ),
    )


async def _unexpected_error(_request: Request, _exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content=_error_payload(
            500,
            code="internal_error",
            message="服务未能完成请求。",
            next_action="保留请求信息并稍后重试。",
        ),
    )


def install_api_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(Exception, _unexpected_error)
