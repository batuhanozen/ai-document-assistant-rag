from urllib.parse import urlsplit

from starlette.responses import JSONResponse


class RequestGuard:
    """Bound bodies before JSON parsing; prevent browser cross-origin mutations."""

    def __init__(self, app, upload_limit: int):
        self.app = app
        self.upload_limit = upload_limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = {key.decode().lower(): value.decode() for key, value in scope["headers"]}

        async def reject(code, message, status):
            await JSONResponse({"error": {"code": code, "message": message}}, status_code=status)(
                scope, receive, send
            )

        if scope["method"] in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = headers.get("origin")
            if origin and urlsplit(origin).netloc != headers.get("host"):
                return await reject("origin_rejected", "Cross-origin writes are not allowed.", 403)
            limit = self.upload_limit if scope["path"] == "/api/documents" else 16384
            length = headers.get("content-length")
            if length:
                try:
                    if int(length) < 0:
                        raise ValueError
                    if int(length) > limit:
                        return await reject(
                            "request_too_large", "Request exceeds the size limit.", 413
                        )
                except ValueError:
                    return await reject("invalid_content_length", "Invalid Content-Length.", 400)
            body = bytearray()
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                body.extend(message.get("body", b""))
                if len(body) > limit:
                    return await reject("request_too_large", "Request exceeds the size limit.", 413)
                if not message.get("more_body", False):
                    break
            consumed = False

            async def bounded_receive():
                nonlocal consumed
                if not consumed:
                    consumed = True
                    return {"type": "http.request", "body": bytes(body), "more_body": False}
                return await receive()

            return await self.app(scope, bounded_receive, send)
        return await self.app(scope, receive, send)


class SecurityHeaders:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        async def secure_send(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend(
                    [
                        (b"x-content-type-options", b"nosniff"),
                        (b"referrer-policy", b"no-referrer"),
                        (b"x-frame-options", b"DENY"),
                        (b"cache-control", b"no-store"),
                    ]
                )
                # FastAPI's developer docs load Swagger/ReDoc assets from a CDN.
                if scope.get("path") not in {"/docs", "/redoc", "/docs/oauth2-redirect"}:
                    headers.append(
                        (
                            b"content-security-policy",
                            b"default-src 'self'; "
                            b"script-src 'self'; style-src 'self'; img-src 'self' data:; "
                            b"connect-src 'self'; object-src 'none'; base-uri 'none'; "
                            b"frame-ancestors 'none'; form-action 'self'",
                        )
                    )
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, secure_send)
