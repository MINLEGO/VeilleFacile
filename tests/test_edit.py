import psycopg

from .test_capture import post


def patch(client, sid, **body):
    return client.patch(f"/api/sources/{sid}", json=body)


def test_patch_title_summary_no_llm_summary_and_reindexes(client, fakes, settings):
    sid = post(client).json()["id"]
    calls = fakes["llm"].summarize_calls
    s = patch(client, sid, title="Zebra title", summary="## What it is\nstripes").json()
    assert s["title"] == "Zebra title" and s["summary"].endswith("stripes")
    assert fakes["llm"].summarize_calls == calls
    with psycopg.connect(settings.database_url) as c:
        hit = c.execute("SELECT count(*) FROM sources WHERE search_text @@ plainto_tsquery('english','zebra')")
        assert hit.fetchone()[0] == 1
        emb = c.execute("SELECT embedding::text FROM sources").fetchone()[0]
    assert emb.startswith("[")


def test_patch_keyword_rules(client):
    sid = post(client, keywords=["Mine"]).json()["id"]  # generated [fake], manual [Mine]
    s = patch(client, sid, remove_keywords=["FAKE", "mine"]).json()
    assert s["keywords"] == [] and [w.lower() for w in s["rejected_keywords"]] == ["fake"] and s["manual_keywords"] == []
    s = patch(client, sid, add_keywords=["Fake"]).json()
    assert s["manual_keywords"] == ["Fake"] and s["rejected_keywords"] == [] and s["keywords"] == ["fake"]
    s = patch(client, sid, keywords=["Only"]).json()
    assert s["manual_keywords"] == ["Only"] and s["rejected_keywords"] == ["fake"] and s["keywords"] == ["Only"]


def test_rejected_keyword_survives_reingest(client):
    sid = post(client).json()["id"]
    patch(client, sid, remove_keywords=["fake"])
    assert post(client).json()["keywords"] == []


def test_patch_404(client):
    assert patch(client, 999, title="x").status_code == 404


def test_text_slice(client):
    sid = post(client, full_text="0123456789").json()["id"]
    assert client.get(f"/api/sources/{sid}/text?start=2&length=3").json() == {"text": "234", "start": 2, "total_length": 10}
    assert client.get(f"/api/sources/{sid}/text").json()["text"] == "0123456789"
    assert client.get("/api/sources/999/text").status_code == 404


def test_delete(client):
    sid = post(client).json()["id"]
    assert client.delete(f"/api/sources/{sid}").status_code == 204
    assert client.get(f"/api/sources/{sid}").status_code == 404
    assert client.delete(f"/api/sources/{sid}").status_code == 404
