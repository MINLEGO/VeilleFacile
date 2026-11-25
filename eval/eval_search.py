"""Measure search quality (hit@5, MRR) on the Jeu de reference against the deployed API.

Config (env): API_BASE_URL, API_KEY (required); EMBEDDING_MODEL, SUMMARY_MODEL (recorded in history).
Usage: uv run python eval/eval_search.py [--queries eval/queries.yaml] [--history eval/history.csv]

Queries file: deliberately tiny YAML subset, parsed by hand (stdlib only, no PyYAML).
  - A list of items, each starting with "- " at column 0.
  - Item keys, two-space indent: `query` (text), `type` (proper_noun | concept | french),
    `expected` (list).
  - `expected:` is followed by lines "    - <canonical URL>".
  - Scalars may be bare or wrapped in "..." or '...'. Lines starting with # and blank lines are ignored.
  - Anything else (nesting, flow style, anchors, multi-line strings) is a ParseError.
  shortcut: this subset, upgrade to PyYAML (or JSON) if the format grows.
"""

import argparse
import csv
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

TYPES = ("proper_noun", "concept", "french")
MODES = ("hybrid", "semantic", "text")
RRF_K = 60  # recorded in history.csv; the server's RRF constant
HISTORY_FIELDS = (
    ["date", "embedding_model", "summary_model", "k", "n_queries"]
    + [f"{m}_{metric}" for m in MODES for metric in ("hit5", "mrr")]
)
HERE = Path(__file__).resolve().parent


class ParseError(ValueError):
    pass


def _scalar(text):
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    return text


def parse_queries(text):
    items = []
    list_key = None
    for n, raw in enumerate(text.splitlines(), 1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())
        if indent == 0:
            if not stripped.startswith("- "):
                raise ParseError(f"line {n}: expected a '- ' item")
            items.append({})
            list_key = None
            stripped = stripped[2:].strip()
        elif not items:
            raise ParseError(f"line {n}: indented line before any item")
        if stripped.startswith("- "):
            if list_key is None:
                raise ParseError(f"line {n}: list item outside of a list key")
            items[-1][list_key].append(_scalar(stripped[2:]))
            continue
        key, sep, value = stripped.partition(":")
        if not sep:
            raise ParseError(f"line {n}: expected 'key: value'")
        key, value = key.strip(), value.strip()
        if value:
            items[-1][key] = _scalar(value)
            list_key = None
        else:
            items[-1][key] = []
            list_key = key
    for i, item in enumerate(items, 1):
        for field in ("query", "type", "expected"):
            if field not in item:
                raise ParseError(f"item {i}: missing '{field}'")
        if item["type"] not in TYPES:
            raise ParseError(f"item {i}: unknown type {item['type']!r}")
        if not item["expected"]:
            raise ParseError(f"item {i}: 'expected' is empty")
    return items


def score_query(ranked, expected, k=5):
    top = ranked[:k]
    ranks = [top.index(url) + 1 for url in expected if url in top]
    return {
        "hit": bool(ranks),
        "rr": 1 / min(ranks) if ranks else 0.0,
        "missing": [url for url in expected if url not in top],
    }


def _summarize(scores):
    n = len(scores)
    if n == 0:
        return {"n": 0, "hit5": 0.0, "mrr": 0.0}
    return {
        "n": n,
        "hit5": sum(s["hit"] for s in scores) / n,
        "mrr": sum(s["rr"] for s in scores) / n,
    }


def search_url(base_url, query, mode, limit):
    qs = urllib.parse.urlencode({"q": query, "mode": mode, "limit": limit})
    return f"{base_url.rstrip('/')}/api/sources?{qs}"


def run_eval(items, base_url, fetch, modes=MODES, limit=5):
    """fetch(url) -> parsed JSON of GET /api/sources. Missing expected Sources count as misses + warnings."""
    report = {}
    for mode in modes:
        typed_scores, warnings = [], []
        for item in items:
            data = fetch(search_url(base_url, item["query"], mode, limit))
            ranked = [r["canonical_url"] for r in data["results"]]
            score = score_query(ranked, item["expected"], k=limit)
            for url in score["missing"]:
                warnings.append(f"[{mode}] {item['query']!r}: expected Source not in top {limit}: {url}")
            typed_scores.append((item["type"], score))
        report[mode] = {
            "overall": _summarize([s for _, s in typed_scores]),
            "by_type": {t: _summarize([s for ty, s in typed_scores if ty == t]) for t in TYPES},
            "warnings": warnings,
        }
    return report


def build_history_row(n_queries, report, embedding_model, summary_model, today=None):
    row = {
        "date": (today or date.today()).isoformat(),
        "embedding_model": embedding_model,
        "summary_model": summary_model,
        "k": RRF_K,
        "n_queries": n_queries,
    }
    for mode in report:
        row[f"{mode}_hit5"] = round(report[mode]["overall"]["hit5"], 4)
        row[f"{mode}_mrr"] = round(report[mode]["overall"]["mrr"], 4)
    return row


def append_history(path, row):
    path = Path(path)
    is_new = not path.exists() or path.stat().st_size == 0
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=HISTORY_FIELDS)
        if is_new:
            writer.writeheader()
        writer.writerow(row)


def make_http_fetch(api_key, timeout=30):
    def fetch(url):
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {api_key}"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    return fetch


def print_report(report, n_queries):
    print(f"{n_queries} queries, limit=5")
    for mode, data in report.items():
        o = data["overall"]
        print(f"{mode:9} hit@5={o['hit5']:.3f} MRR={o['mrr']:.3f} (n={o['n']})")
        for t, s in data["by_type"].items():
            print(f"  {t:12} hit@5={s['hit5']:.3f} MRR={s['mrr']:.3f} (n={s['n']})")
        for w in data["warnings"]:
            print(f"WARNING: {w}", file=sys.stderr)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--queries", default=HERE / "queries.yaml")
    parser.add_argument("--history", default=HERE / "history.csv")
    args = parser.parse_args(argv)

    base_url = os.environ.get("API_BASE_URL")
    api_key = os.environ.get("API_KEY")
    if not base_url or not api_key:
        sys.exit("API_BASE_URL and API_KEY must be set")

    items = parse_queries(Path(args.queries).read_text(encoding="utf-8"))
    report = run_eval(items, base_url, make_http_fetch(api_key))
    print_report(report, len(items))
    row = build_history_row(
        len(items), report, os.environ.get("EMBEDDING_MODEL", ""), os.environ.get("SUMMARY_MODEL", "")
    )
    append_history(args.history, row)
    print(f"appended to {args.history}")


if __name__ == "__main__":
    main()
