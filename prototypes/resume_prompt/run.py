"""PROTOTYPE, throwaway. Ticket "Prompt du Résumé structuré" (MINLEGO/VeilleFacile#6).

Runs the candidate Résumé + Mots-clés prompt on real Sources so you can judge the output.

    $env:OPENROUTER_API_KEY = "<your key>"
    python prototypes/resume_prompt/run.py prototypes/resume_prompt/sources.txt

sources.txt: one Source per line.
  - GitHub / Hugging Face URL alone -> Récupération par URL (README fetched).
  - `URL | path/to/text.txt` -> Capture (Texte intégral read from the file: transcript, article...).
  - Any other URL alone -> crude HTML-to-text fetch (good enough for a blog article).
Results go to prototypes/resume_prompt/out/<timestamp>.md. One LLM request per Source (free quota: 50/day).
"""
import html, json, os, re, sys, time, urllib.request
from pathlib import Path
from urllib.parse import urlparse

MODEL = os.environ.get("MODEL", "nvidia/nemotron-3.5-lightning:free")
LANG = os.environ.get("LANG_RESUME", "français")  # language of the Résumé; Mots-clés stay in their original form
MAX_CHARS = 100_000  # shortcut: hard truncation of Texte intégral, upgrade if long transcripts lose their end

PROMPT = """You write the summary card of a saved web resource for a personal tech watch (veille) database.
The card must let the reader decide, months later, whether the resource is worth reopening, and make it findable by search.

Resource: {title}
URL: {url}
Site: {site}

Full text (may be truncated):
<<<
{text}
>>>

Answer in {lang}, using EXACTLY this format and nothing else (no preamble, no closing remark):

## De quoi ça parle
<2-3 sentences: what the resource is and what it does/claims, concretely.>

## Pourquoi c'est intéressant
<1-2 sentences: what is new, notable, or useful compared to the usual. No hype words.>

## Points clés
- <3 to 6 bullets: concrete facts, numbers, techniques, limitations>

## Pour qui
<1 sentence: who should reopen this, and for what need.>

## Mots-clés
<8 to 15 comma-separated keywords. Mostly proper nouns as written in the source (tools, models, libraries, companies, authors, datasets, benchmarks), plus a few topic terms. No generic words like "AI" or "tool".>
"""

SECTIONS = ["De quoi ça parle", "Pourquoi c'est intéressant", "Points clés", "Pour qui", "Mots-clés"]


def get(url, accept=None):
    req = urllib.request.Request(url, headers={"User-Agent": "veillefacile-prototype", **({"Accept": accept} if accept else {})})
    if "api.github.com" in url and os.environ.get("GITHUB_TOKEN"):
        req.add_header("Authorization", f"Bearer {os.environ['GITHUB_TOKEN']}")
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", "replace")


def fetch(url, path):
    """Return (title, site, text)."""
    u = urlparse(url)
    site = u.netloc.removeprefix("www.")
    parts = [p for p in u.path.split("/") if p]
    if path:
        return parts[-1] if parts else site, site, Path(path).read_text(encoding="utf-8")
    if site == "github.com":
        repo = "/".join(parts[:2])
        meta = json.loads(get(f"https://api.github.com/repos/{repo}"))
        readme = get(f"https://api.github.com/repos/{repo}/readme", "application/vnd.github.raw")
        return repo, site, f"Description: {meta.get('description')}\nTopics: {', '.join(meta.get('topics', []))}\n\n{readme}"
    if site == "huggingface.co":
        kind = parts[0] if parts[0] in ("datasets", "spaces") else "models"
        rid = "/".join(parts[1:3] if kind != "models" else parts[:2])
        prefix = "" if kind == "models" else f"{kind}/"
        meta = json.loads(get(f"https://huggingface.co/api/{kind}/{rid}"))
        readme = get(f"https://huggingface.co/{prefix}{rid}/raw/main/README.md")
        return rid, site, f"Tags: {', '.join(meta.get('tags', []))}\n\n{readme}"
    page = get(url)
    m = re.search(r"<title[^>]*>(.*?)</title>", page, re.S | re.I)
    page = re.sub(r"(?is)<(script|style|nav|header|footer)[^>]*>.*?</\1>", " ", page)
    text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", page)))
    return html.unescape(m.group(1).strip()) if m else site, site, text


def llm(prompt):
    body = json.dumps({"model": MODEL, "messages": [{"role": "user", "content": prompt}], "temperature": 0.2}).encode()
    req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", body, {
        "Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}", "Content-Type": "application/json"})
    t = time.time()
    with urllib.request.urlopen(req, timeout=300) as r:
        data = json.loads(r.read())
    return data["choices"][0]["message"]["content"] or "", time.time() - t, data.get("usage", {})


def parse(out):
    """Split the answer on the expected headings. Missing section -> None (a parse failure the prototype must show)."""
    found = {}
    for chunk in re.split(r"^##\s*", out, flags=re.M)[1:]:
        head, _, body = chunk.partition("\n")
        found[head.strip()] = body.strip()
    res = {s: found.get(s) for s in SECTIONS}
    res["Mots-clés"] = [k.strip() for k in res["Mots-clés"].split(",") if k.strip()] if res["Mots-clés"] else None
    return res


def main():
    lines = [l.strip() for l in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]
    out_dir = Path(__file__).parent / "out"
    out_dir.mkdir(exist_ok=True)
    report = [f"# Run {time.strftime('%Y-%m-%d %H:%M')} — {MODEL} — langue : {LANG}\n"]
    for line in lines:
        url, _, path = (s.strip() for s in line.partition("|"))
        print(f"\n=== {url}")
        try:
            title, site, text = fetch(url, path)
            out, secs, usage = llm(PROMPT.format(title=title, url=url, site=site, text=text[:MAX_CHARS], lang=LANG))
        except Exception as e:  # keep going: one broken Source must not kill the run
            print(f"ERREUR : {e}")
            report.append(f"## {url}\n\nERREUR : {e}\n")
            continue
        res = parse(out)
        missing = [s for s in SECTIONS if not res[s]]
        status = f"OK" if not missing else f"SECTIONS MANQUANTES : {missing}"
        info = f"{site} · {len(text)} car. (tronqué)" if len(text) > MAX_CHARS else f"{site} · {len(text)} car."
        block = f"## {title}\n\n{url} · {info} · {secs:.1f}s · tokens {usage.get('prompt_tokens')}/{usage.get('completion_tokens')} · {status}\n\n{out.strip()}\n"
        if res["Mots-clés"]:
            block += f"\n_Mots-clés parsés ({len(res['Mots-clés'])}) :_ {res['Mots-clés']}\n"
        print(block)
        report.append(block)
    f = out_dir / f"{time.strftime('%Y%m%d-%H%M%S')}.md"
    f.write_text("\n---\n\n".join(report), encoding="utf-8")
    print(f"\nRapport : {f}")


if __name__ == "__main__":
    main()
