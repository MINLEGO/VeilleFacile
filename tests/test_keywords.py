"""Keyword rules, observed through POST / PATCH / GET."""
from .test_capture import post
from .test_edit import patch


def test_effective_is_generated_minus_rejected_plus_manual_case_insensitive(client, fakes):
    fakes["llm"].keywords = ["RAG", "Llama", "x"]
    sid = post(client, keywords=["rag", "Mine"]).json()["id"]
    s = patch(client, sid, remove_keywords=["X"]).json()
    assert s["keywords"] == ["RAG", "Llama", "Mine"]
    assert client.get(f"/api/sources/{sid}").json()["keywords"] == ["RAG", "Llama", "Mine"]


def test_remove_generated_rejects_it_and_manual_just_leaves(client, fakes):
    fakes["llm"].keywords = ["a", "b"]
    sid = post(client, keywords=["c"]).json()["id"]
    s = patch(client, sid, remove_keywords=["A", "C"]).json()
    assert s["rejected_keywords"] == ["A", "C"] and s["manual_keywords"] == [] and s["keywords"] == ["b"]


def test_add_rehabilitates_rejected(client, fakes):
    fakes["llm"].keywords = ["a"]
    sid = post(client).json()["id"]
    patch(client, sid, remove_keywords=["a"])
    s = patch(client, sid, add_keywords=["A"]).json()
    assert s["rejected_keywords"] == [] and s["keywords"] == ["a"]


def test_replace_rejects_generated_absent_from_list(client, fakes):
    fakes["llm"].keywords = ["a", "b"]
    sid = post(client).json()["id"]
    s = patch(client, sid, keywords=["B", "z"]).json()
    assert s["manual_keywords"] == ["B", "z"] and s["rejected_keywords"] == ["a"] and s["keywords"] == ["b", "z"]


def test_reingest_regenerates_but_keeps_manual_and_rejected(client, fakes):
    fakes["llm"].keywords = ["old"]
    sid = post(client, keywords=["m"]).json()["id"]
    patch(client, sid, remove_keywords=["bad"])
    fakes["llm"].keywords = ["new", "bad"]
    s = post(client).json()
    assert s["generated_keywords"] == ["new", "bad"] and s["manual_keywords"] == ["m"]
    assert s["rejected_keywords"] == ["bad"] and s["keywords"] == ["new", "m"]
