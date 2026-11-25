import os
import uuid

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.conninfo import make_conninfo

from veillefacile.app import create_app
from veillefacile.settings import Settings

from .fakes import FakeGitHub, FakeHuggingFace, FakeLLM

SERVER_URL = os.environ.get("TEST_DATABASE_URL", "postgresql://postgres:postgres@localhost:55432/postgres")
API_KEY = "test-key"
AUTH = {"Authorization": f"Bearer {API_KEY}"}


@pytest.fixture(scope="session")
def database_url():
    """A uniquely named database per session, so parallel worktrees don't collide."""
    name = f"vf_test_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(SERVER_URL, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    yield make_conninfo(SERVER_URL, dbname=name)
    with psycopg.connect(SERVER_URL, autocommit=True) as admin:
        admin.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name)))


@pytest.fixture
def settings(database_url):
    return Settings(api_key=API_KEY, database_url=database_url, skip_model_check=True)


@pytest.fixture
def fakes():
    return {"llm": FakeLLM(), "github": FakeGitHub(), "hf": FakeHuggingFace()}


@pytest.fixture
def client(settings, fakes):
    """TestClient with the API key preset; migrations applied, sources truncated."""
    with TestClient(create_app(settings, **fakes), headers=AUTH) as c:
        with psycopg.connect(settings.database_url) as conn:
            conn.execute("TRUNCATE sources, query_embeddings RESTART IDENTITY")
        yield c
