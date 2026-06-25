import json
import time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class IntegrationApiResponseMiddleware(BaseHTTPMiddleware):
    """Wrap /api/integration/v1/ JSON responses in a standard envelope.

    Envelope: { code: int, message: str, data: any | null, timestamp: int_ms }
    """

    PREFIX = "/api/integration/v1/"

    async def dispatch(self, request: Request, call_next) -> Response:
        if not request.url.path.startswith(self.PREFIX):
            return await call_next(request)

        response = await call_next(request)

        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type:
            return response

        body = b""
        try:
            body = response.body
        except AttributeError:
            try:
                body = b"".join([chunk async for chunk in response.body_iterator])
            except Exception:
                return response

        if not body:
            return response

        try:
            original_payload = json.loads(body)
        except (json.JSONDecodeError, TypeError):
            return response

        is_success = 200 <= response.status_code < 300

        if is_success:
            message = "success"
            data = original_payload
        else:
            detail = original_payload.get("detail", "Unknown error")
            message = detail if isinstance(detail, str) else json.dumps(detail, ensure_ascii=False)
            data = None

        wrapped = {
            "code": response.status_code,
            "message": message,
            "data": data,
            "timestamp": int(time.time() * 1000),
        }

        return JSONResponse(content=wrapped, status_code=response.status_code)
