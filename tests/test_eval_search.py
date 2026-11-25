import csv

import pytest

from eval_search import (
    HISTORY_FIELDS,
    ParseError,
    append_history,
    parse_queries,
    run_eval,
    score_query,
)

YAML_SAMPLE = """\
# comment line
- query: "pgvector HNSW"
  type: proper_noun
  expected:
    - https://github.com/pgvector/pgvector
- query: retrieval augmented generation
  type: concept
  expected:
    - https://huggingface.co/blog/rag
    - https://example.com/rag-intro
- query: "recherche sémantique"
  type: french
  expected:
    - https://example.com/semantic
"""


def test_parse_queries_reads_subset():
    items = parse_queries(YAML_SAMPLE)
    assert len(items) == 3
    assert items[0] == {
        "query": "pgvector HNSW",
        "type": "proper_noun",
        "expected": ["https://github.com/pgvector/pgvector"],
    }
    assert items[1]["expected"] == ["https://huggingface.co/blog/rag", "https://example.com/rag-intro"]
    assert items[2]["query"] == "recherche sémantique"


def test_parse_queries_rejects_missing_expected():
    with pytest.raises(ParseError):
        parse_queries("- query: x\n  type: concept\n")


def test_parse_queries_rejects_unknown_type():
    with pytest.raises(ParseError):
        parse_queries("- query: x\n  type: banana\n  expected:\n    - https://a.test\n")


def test_score_query_hit_and_reciprocal_rank():
    s = score_query(["https://a", "https://b", "https://c"], ["https://c"], k=5)
    assert s["hit"] is True
    assert s["rr"] == pytest.approx(1 / 3)
    assert s["missing"] == []


def test_score_query_miss_outside_top_k():
    ranked = [f"https://x{i}" for i in range(5)] + ["https://want"]
    s = score_query(ranked, ["https://want"], k=5)
    assert s["hit"] is False
    assert s["rr"] == 0.0
    assert s["missing"] == ["https://want"]


def test_score_query_missing_expected_is_failure_with_warning():
    s = score_query(["https://a"], ["https://gone"], k=5)
    assert s["hit"] is False
    assert s["missing"] == ["https://gone"]


def fake_fetch_factory(results_by_query):
    calls = []

    def fetch(url):
        from urllib.parse import parse_qs, urlparse

        qs = parse_qs(urlparse(url).query)
        calls.append((qs["q"][0], qs["mode"][0], qs["limit"][0]))
        urls = results_by_query[qs["q"][0]]
        return {"results": [{"canonical_url": u} for u in urls], "degraded": False}

    return fetch, calls


def test_run_eval_groups_by_mode_and_type():
    items = parse_queries(YAML_SAMPLE)
    results = {
        "pgvector HNSW": ["https://github.com/pgvector/pgvector"],
        "retrieval augmented generation": ["https://z", "https://example.com/rag-intro"],
        "recherche sémantique": ["https://nope"],
    }
    fetch, calls = fake_fetch_factory(results)
    report = run_eval(items, "http://api", fetch, modes=("hybrid", "text"), limit=5)

    hybrid = report["hybrid"]
    assert hybrid["overall"]["hit5"] == pytest.approx(2 / 3)
    assert hybrid["overall"]["mrr"] == pytest.approx((1 + 0.5 + 0) / 3)
    assert hybrid["by_type"]["proper_noun"]["hit5"] == 1.0
    assert hybrid["by_type"]["french"]["hit5"] == 0.0
    assert any("https://example.com/semantic" in w for w in hybrid["warnings"])
    assert set(c[1] for c in calls) == {"hybrid", "text"}
    assert all(c[2] == "5" for c in calls)


def test_append_history_writes_header_once(tmp_path):
    path = tmp_path / "history.csv"
    row = {f: "" for f in HISTORY_FIELDS}
    row.update(date="2026-01-01", n_queries="3", k="60")
    append_history(path, row)
    append_history(path, row)
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    assert rows[0] == HISTORY_FIELDS
    assert len(rows) == 3
    assert rows[1][HISTORY_FIELDS.index("k")] == "60"
