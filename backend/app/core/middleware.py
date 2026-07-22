import time
import uuid
import json
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from loguru import logger


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """
    FastAPI Middleware for structured JSON logging, correlation request IDs,
    latency tracking, and error handling.
    """
    async def dispatch(self, request: Request, call_next) -> Response:
        # 1. Tracing: Generate or extract Request ID
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        
        # Bind Request ID dynamically for all thread-local logs in the request context
        logger.configure(extra={"request_id": request_id})

        start_time = time.perf_counter()
        
        client_ip = request.client.host if request.client else "unknown_ip"
        path = request.url.path
        method = request.method

        logger.bind(
            request_id=request_id,
            client_ip=client_ip,
            path=path,
            method=method
        ).info(f"Incoming Request: {method} {path}")

        try:
            # 2. Execute target route
            response = await call_next(request)
            
            # Attach X-Request-ID response header
            response.headers["X-Request-ID"] = request_id

            duration = time.perf_counter() - start_time
            logger.bind(
                request_id=request_id,
                status_code=response.status_code,
                duration_seconds=round(duration, 4),
            ).info(f"Request Completed: {method} {path} with status {response.status_code}")
            
            return response

        except Exception as e:
            # 3. Graceful Error Handling & Tracing Logs
            duration = time.perf_counter() - start_time
            logger.bind(
                request_id=request_id,
                duration_seconds=round(duration, 4)
            ).error(f"Request FAILED: {method} {path} - Error: {e}")

            # Structured audit-ready error response
            return JSONResponse(
                status_code=500,
                content={
                    "detail": "An internal server error occurred.",
                    "request_id": request_id,
                    "error_class": e.__class__.__name__
                }
            )
