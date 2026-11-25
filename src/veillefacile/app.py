import secrets
from contextlib import asynccontextmanager

import psycopg
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .clients import GitHubClient, HuggingFaceClient, OpenRouterClient
from fastapi.responses import JSONResponse

from .db import migrate
from .errors import CaptureRequired, QuotaError, UpstreamError
from .ingestion import IngestionService
from .repository import SourceRepository
from .routes import sources
from .settings import Settings

_bearer = HTTPBearer(auto_error=False)


def require_key(request: Request, creds: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> None:
    key = request.app.state.settings.api_key
    if creds is None or not secrets.compare_digest(creds.credentials, key):
        raise HTTPException(401, "Invalid or missing API key", headers={"WWW-Authenticate": "Bearer"})


def create_app(settings: Settings | None = None, *, llm=None, github=None, hf=None) -> FastAPI:
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if not settings.skip_migrations:
            migrate(settings.database_url, settings.migrations_dir)
        yield

    app = FastAPI(lifespan=lifespan)
    app.state.settings = settings
    app.state.llm = llm or OpenRouterClient(settings.openrouter_api_key, settings.summary_model, settings.embedding_model)
    app.state.github = github or GitHubClient(settings.github_token)
    app.state.hf = hf or HuggingFaceClient(settings.hf_token)

    app.state.repo = SourceRepository(settings.database_url)
    app.state.ingestion = IngestionService(
        app.state.repo, app.state.llm, {"github.com": app.state.github, "huggingface.co": app.state.hf},
        settings.embedding_model)

    @app.exception_handler(UpstreamError)
    async def _upstream(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=502)

    @app.exception_handler(QuotaError)
    async def _quota(request, exc):
        return JSONResponse({"detail": "Quota exhausted"}, status_code=503,
                            headers={"Retry-After": str(exc.retry_after)})

    @app.exception_handler(CaptureRequired)
    async def _capture(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=422)

    api = APIRouter(prefix="/api")

    @api.get("/health")
    def health(response: Response):
        try:
            with psycopg.connect(settings.database_url, connect_timeout=3) as conn:
                conn.execute("SELECT 1")
        except psycopg.Error:
            response.status_code = 503
            return {"status": "unavailable"}
        return {"status": "ok"}

    # Every other /api route goes on this router (add routes before include_router): it enforces the Bearer key.
    protected = APIRouter(prefix="/api", dependencies=[Depends(require_key)])

    @protected.get("/ping")
    def ping():
        return {"ping": "pong"}

    protected.include_router(sources.router)  # one line per route module

    app.include_router(api)
    app.include_router(protected)
    return app
