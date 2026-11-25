import asyncio

import psycopg
import pytest
from fastapi.testclient import TestClient

from veillefacile.app import create_app
from veillefacile.errors import UpstreamError
from veillefacile.reembed import reembed
from veillefacile.repository import SourceRepository

from .conftest import AUTH
from .fakes import DIM

NEW = "new/model"


def seed(client, settings, n):
    for i in range(n):
        r = client.post("/api/sources", json={"url": f"https://a.com/{i}", "title": f"T{i}", "summary": "s",
                                              "full_text": "x"})
        assert r.status_code == 201, r.text
    with psycopg.connect(settings.database_url) as conn:
        conn.execute("UPDATE sources SET embedding_model = 'old'")


def stale(settings):
    with psycopg.connect(settings.database_url) as conn:
        return conn.execute("SELECT count(*) FROM sources WHERE embedding_model IS DISTINCT FROM %s",
                            (NEW,)).fetchone()[0]


class CountingLLM:
    def __init__(self, inner, fail_on_call=None):
        self.inner, self.fail_on_call, self.calls = inner, fail_on_call, []

    async def embed(self, texts):
        self.calls.append(len(texts))
        if self.fail_on_call == len(self.calls):
            raise UpstreamError("boom")
        return await self.inner.embed(texts)


def run(settings, llm, answer="o"):
    out = []
    code = asyncio.run(reembed(SourceRepository(settings.database_url), llm, NEW,
                               confirm=lambda prompt: answer, out=out.append))
    return code, "\n".join(out)


def test_plan_confirmation_batches_of_32(client, settings, fakes):
    seed(client, settings, 35)
    llm = CountingLLM(fakes["llm"])
    code, text = run(settings, llm)
    assert code == 0 and stale(settings) == 0
    assert llm.calls == [1, 32, 3]  # test call, then batches
    assert NEW in text and str(DIM) in text and "35" in text and "2 appels" in text


def test_declined_changes_nothing(client, settings, fakes):
    seed(client, settings, 2)
    llm = CountingLLM(fakes["llm"])
    assert run(settings, llm, answer="")[0] == 1 and llm.calls == [1] and stale(settings) == 2


def test_resumes_after_interruption(client, settings, fakes):
    seed(client, settings, 40)
    llm = CountingLLM(fakes["llm"], fail_on_call=3)  # test call, batch 1 ok, batch 2 fails
    assert run(settings, llm)[0] == 1
    assert stale(settings) == 8  # first batch of 32 was committed
    llm2 = CountingLLM(fakes["llm"])
    assert run(settings, llm2)[0] == 0 and llm2.calls == [1, 8] and stale(settings) == 0


def test_health_stale_count_and_expiring_model_warning(settings, fakes):
    async def models():
        return [{"id": settings.embedding_model, "expiration_date": "2027-01-01"}]

    with TestClient(create_app(settings, **fakes, models=models), headers=AUTH) as c:
        with psycopg.connect(settings.database_url) as conn:
            conn.execute("TRUNCATE sources RESTART IDENTITY")
            conn.execute("INSERT INTO sources (url, canonical_url, origin_site, title, summary, full_text, "
                         "ingest_mode, embedding_model) VALUES ('u','c','s','t','s','f','capture','old')")
        h = c.get("/api/health").json()
    assert h["status"] == "ok" and h["stale_sources"] == 1 and "expir" in h["warnings"][0]


@pytest.mark.parametrize("listing,n", [([{"id": "other"}], 1),
                                       ([{"id": "nvidia/nemotron-3.5-embed-8b:free", "expiration_date": None}], 0),
                                       (None, 0)])  # None: list unreachable -> ignored
def test_model_check(settings, fakes, listing, n):
    async def fetch():
        if listing is None:
            raise UpstreamError("down")
        return listing

    with TestClient(create_app(settings, **fakes, models=fetch)) as c:
        assert len(c.get("/api/health").json()["warnings"]) == n
