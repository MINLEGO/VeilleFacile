"""`python -m veillefacile.reembed` through its entry point (`main`); effects observed through the API."""
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from veillefacile.app import create_app
from veillefacile.errors import UpstreamError
from veillefacile.reembed import main

from .conftest import AUTH
from .fakes import DIM

NEW = "new/model"


def seed(client, n):
    for i in range(n):
        r = client.post("/api/sources", json={"url": f"https://a.com/{i}", "title": f"T{i}", "summary": "s",
                                              "full_text": "x"})
        assert r.status_code == 201, r.text


def health(settings, fakes):
    with TestClient(create_app(replace(settings, embedding_model=NEW), **fakes), headers=AUTH) as c:
        return c.get("/api/health").json()


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
    code = main(replace(settings, embedding_model=NEW), llm, confirm=lambda prompt: answer, out=out.append)
    return code, "\n".join(out)


def test_plan_confirmation_batches_of_32(client, settings, fakes):
    seed(client, 35)
    llm = CountingLLM(fakes["llm"])
    code, text = run(settings, llm)
    assert code == 0 and health(settings, fakes)["stale_sources"] == 0
    assert llm.calls == [1, 32, 3]  # test call, then batches
    assert NEW in text and str(DIM) in text and "35" in text and "2 appels" in text


def test_declined_changes_nothing(client, settings, fakes):
    seed(client, 2)
    llm = CountingLLM(fakes["llm"])
    assert run(settings, llm, answer="")[0] == 1 and llm.calls == [1]
    assert health(settings, fakes)["stale_sources"] == 2


def test_resumes_after_interruption(client, settings, fakes):
    seed(client, 40)
    llm = CountingLLM(fakes["llm"], fail_on_call=3)  # test call, batch 1 ok, batch 2 fails
    assert run(settings, llm)[0] == 1
    assert health(settings, fakes)["stale_sources"] == 8  # first batch of 32 was committed
    llm2 = CountingLLM(fakes["llm"])
    assert run(settings, llm2)[0] == 0 and llm2.calls == [1, 8]
    assert health(settings, fakes)["stale_sources"] == 0


def test_reembed_keeps_listing_order_and_updated_at(client, settings, fakes):
    seed(client, 3)
    before = client.get("/api/sources").json()["results"]
    assert run(settings, CountingLLM(fakes["llm"]))[0] == 0
    with TestClient(create_app(replace(settings, embedding_model=NEW), **fakes), headers=AUTH) as c:
        after = c.get("/api/sources").json()["results"]
    assert [(s["id"], s["updated_at"]) for s in after] == [(s["id"], s["updated_at"]) for s in before]
    assert all(s["embedding_model"] == NEW for s in after)


def test_reembedded_sources_found_by_semantic_search(client, settings, fakes):
    seed(client, 2)
    run(settings, CountingLLM(fakes["llm"]))
    with TestClient(create_app(replace(settings, embedding_model=NEW), **fakes), headers=AUTH) as c:
        r = c.get("/api/sources", params={"q": "T1 s", "mode": "semantic"}).json()
    assert len(r["results"]) == 2 and r["results"][0]["title"] == "T1"


def test_health_stale_count_and_expiring_model_warning(client, settings, fakes):
    seed(client, 1)

    async def models():
        return [{"id": NEW, "expiration_date": "2027-01-01"},
                *({"id": m} for m in settings.summary_models)]

    with TestClient(create_app(replace(settings, embedding_model=NEW), **fakes, models=models), headers=AUTH) as c:
        h = c.get("/api/health").json()
    assert h["status"] == "ok" and h["stale_sources"] == 1 and len(h["warnings"]) == 1 and "expir" in h["warnings"][0]


@pytest.mark.parametrize("listing,n", [(["other"], 3), (["emb", "m1", "m2"], 0), (None, 0)])  # None: unreachable
def test_model_check(settings, fakes, listing, n):
    s = replace(settings, embedding_model="emb", summary_model="m1,m2")

    async def fetch():
        if listing is None:
            raise UpstreamError("down")
        return [{"id": i, "expiration_date": None} for i in listing]

    with TestClient(create_app(s, **fakes, models=fetch)) as c:
        assert len(c.get("/api/health").json()["warnings"]) == n
