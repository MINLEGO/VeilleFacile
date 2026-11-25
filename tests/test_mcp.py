import json
from dataclasses import replace

import psycopg
import pytest
from fastapi.testclient import TestClient

from veillefacile.app import create_app

from .conftest import AUTH

HDR = {**AUTH, "Accept": "application/json, text/event-stream"}


def rpc(client, method, params=None, headers=HDR):
    return client.post("/mcp", headers=headers, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}})


def call(client, tool, **args):
    body = rpc(client, "tools/call", {"name": tool, "arguments": args}).json()["result"]
    return body["isError"], (body["content"][0]["text"] if body["isError"] else json.loads(body["content"][0]["text"]))


def test_requires_bearer(client):
    assert rpc(client, "tools/list", headers={**HDR, "Authorization": ""}).status_code == 401
    assert rpc(client, "tools/list", headers={**HDR, "Authorization": "Bearer nope"}).status_code == 401


def test_default_disables_update_and_delete(client):
    names = {t["name"] for t in rpc(client, "tools/list").json()["result"]["tools"]}
    assert names == {"search_sources", "get_source", "get_full_text", "add_source"}


@pytest.fixture
def full_client(settings, fakes):
    with TestClient(create_app(replace(settings, mcp_disabled_tools=""), **fakes), headers=AUTH) as c:
        with psycopg.connect(settings.database_url) as conn:
            conn.execute("TRUNCATE sources RESTART IDENTITY")
        yield c


def test_all_tools_flow(full_client):
    c = full_client
    assert len(rpc(c, "tools/list").json()["result"]["tools"]) == 6
    err, src = call(c, "add_source", url="https://example.com/a", full_text="0123456789", title="Zebra")
    assert not err and "full_text" not in src
    sid = src["id"]
    assert call(c, "get_source", source_id=sid)[1]["title"] == "Zebra"
    assert call(c, "get_full_text", source_id=sid, start=2, length=3)[1] == {"text": "234", "start": 2, "total_length": 10}
    assert [r["id"] for r in call(c, "search_sources", q="zebra", mode="text")[1]["results"]] == [sid]
    assert call(c, "update_source", source_id=sid, title="Lion")[1]["title"] == "Lion"
    assert call(c, "delete_source", source_id=sid)[1] == {"deleted": sid}
    assert call(c, "get_source", source_id=sid)[0] is True
