import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.middleware import RequestGuard, SecurityHeaders
from app.api.routes import router
from app.config import Settings
from app.database import create_database
from app.errors import AppError
from app.services.assistant import Assistant
from app.services.embeddings import build_embedder
from app.services.llm import DemoProvider, OpenAICompatibleProvider
from app.services.vectors import VectorStore

STATIC_DIR = Path(__file__).parent / "static"
logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None, service: Assistant | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logging.basicConfig(level=settings.log_level, format="%(levelname)s %(name)s: %(message)s")
        # Dependency loggers can contain URLs or provider payloads; keep them quiet.
        for name in ("httpx", "httpcore", "pypdf", "chromadb", "sentence_transformers"):
            logging.getLogger(name).setLevel(logging.ERROR)
        if service is None:
            sessions = create_database(settings.data_dir)
            embedder = build_embedder(settings)
            vectors = VectorStore(settings.data_dir / "chroma")
            provider = (
                DemoProvider()
                if settings.app_mode == "demo"
                else OpenAICompatibleProvider(settings)
            )
            app.state.assistant = Assistant(settings, sessions, embedder, vectors, provider)
        else:
            app.state.assistant = service
        logger.info(
            "Assistant started in %s mode (%s)", settings.app_mode, settings.embedding_backend
        )
        try:
            yield
        finally:
            app.state.assistant.provider.close()
            app.state.assistant.sessions.kw["bind"].dispose()

    app = FastAPI(title="AI Document Assistant", version="0.1.0", lifespan=lifespan)
    app.add_middleware(RequestGuard, upload_limit=settings.max_upload_mb * 1024 * 1024)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]"])
    app.add_middleware(SecurityHeaders)

    @app.exception_handler(AppError)
    async def application_error(_request: Request, exc: AppError):
        return JSONResponse(
            {"error": {"code": exc.code, "message": exc.message}}, status_code=exc.status
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, _exc: RequestValidationError):
        return JSONResponse(
            {
                "error": {
                    "code": "validation_error",
                    "message": "Invalid input. Check the fields and their documented limits.",
                }
            },
            status_code=422,
        )

    @app.exception_handler(HTTPException)
    async def http_error(_request: Request, exc: HTTPException):
        return JSONResponse(
            {"error": {"code": "http_error", "message": str(exc.detail)}},
            status_code=exc.status_code,
            headers=exc.headers,
        )

    @app.exception_handler(Exception)
    async def unexpected_error(_request: Request, exc: Exception):
        logger.error("Unhandled request error (%s)", type(exc).__name__)
        return JSONResponse(
            {
                "error": {
                    "code": "internal_error",
                    "message": "An unexpected error occurred. Please try again.",
                }
            },
            status_code=500,
        )

    app.include_router(router)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC_DIR / "index.html")

    return app
