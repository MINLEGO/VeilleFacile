import secrets
from contextlib import asynccontextmanager

import psycopg
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .clients import GitHubClient, HuggingFaceClient, OpenRouterClient
from .db import migrate
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
    app.state.hf = hf or HuggingFaceClient()

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

    app.include_router(api)
    app.include_router(protected)
    return app
