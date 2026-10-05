import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy import text
from starlette.responses import Response
from collections.abc import Awaitable, Callable

from app.core.config import settings
from app.core.database import engine
from app.routers import auth, favorites, history, playlists, sounds
from app.routers.sounds import limiter

@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    await sounds.tiktok_service.close()


app = FastAPI(title=settings.app_name, version="1.0.0", description="Your personal sound library.", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_error(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(status_code=429, content={"success": False, "error": {"code": "RATE_LIMITED", "message": "Please wait a moment before analyzing another video."}})


@app.middleware("http")
async def limit_request_size(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit() and int(content_length) > 1_048_576:
        return JSONResponse(status_code=413, content={"success": False, "error": {"code": "REQUEST_TOO_LARGE", "message": "This request is too large."}})
    return await call_next(request)


@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    detail = exc.detail
    if isinstance(detail, dict) and "code" in detail and "message" in detail:
        error = detail
    else:
        error = {"code": "HTTP_ERROR", "message": str(detail)}
    return JSONResponse(status_code=exc.status_code, content={"success": False, "error": error}, headers=exc.headers)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"success": False, "error": {"code": "VALIDATION_ERROR", "message": "Check the submitted information and try again."}})


app.include_router(auth.router, prefix="/api/v1")
app.include_router(sounds.router, prefix="/api/v1")
app.include_router(playlists.router, prefix="/api/v1")
app.include_router(favorites.router, prefix="/api/v1")
app.include_router(history.router, prefix="/api/v1")


@app.exception_handler(Exception)
async def internal_error(request: Request, exc: Exception) -> JSONResponse:
    logging.getLogger("vorha.api").exception("Unhandled request error", exc_info=exc)
    return JSONResponse(status_code=500, content={"success": False, "error": {"code": "INTERNAL_SERVER_ERROR", "message": "Something went wrong. Please try again."}})


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok", "app": settings.app_name}


@app.get("/health/ready", tags=["health"])
def readiness() -> dict[str, str]:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return {"status": "ready", "app": settings.app_name}
