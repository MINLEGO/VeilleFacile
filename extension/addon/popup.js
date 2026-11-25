let tabId;
const root = document.getElementById("root");
const el = (tag, text, cls) => Object.assign(document.createElement(tag), { textContent: text, className: cls || "" });

const STALE_MS = 2 * 60 * 1000; // pending older than this: background was killed mid-send
const send = (type) => browser.runtime.sendMessage({ type, tabId });

function render(r) {
  root.replaceChildren();
  if (!r || r.status === "pending") return void root.append(el("p", `Envoi… ${r?.step || ""}`));
  if (r.status === "error") {
    root.append(el("p", r.error));
    if (r.action === "options") {
      const b = el("button", "Ouvrir les options");
      b.onclick = () => browser.runtime.openOptionsPage();
      root.append(b);
    }
    if (r.action === "retry" || r.action === "reextract") {
      const b = el("button", "Réessayer");
      // reextract = page not loaded yet: redo the whole capture, not just the POST
      b.onclick = () => send(r.action === "retry" ? "retry" : "capture");
      root.append(b);
    }
    root.append(resend());
    return;
  }
  const s = r.source;
  root.append(el("h2", r.created ? "Ajoutée" : "Mise à jour"), el("strong", s.title || s.url), el("p", s.origin_site, "muted"), el("p", s.summary || ""));
  if (s.keywords?.length) root.append(el("p", s.keywords.join(", "), "muted"));
  for (const w of r.warnings || []) root.append(el("p", `Avertissement : ${w}`, "muted"));
  root.append(resend());
}

function resend() {
  const b = el("button", "Renvoyer");
  b.onclick = () => send("capture");
  return b;
}

(async () => {
  const [tab] = await browser.tabs.query({ active: true, currentWindow: true });
  tabId = tab.id;
  const key = `result:${tab.id}`;
  browser.storage.onChanged.addListener((ch) => ch[key] && render(ch[key].newValue));
  // Reopening shows the last result; a capture starts only when none is stored (or the pending one is stale).
  const stored = (await browser.storage.session.get(key))[key];
  if (stored && !(stored.status === "pending" && Date.now() - stored.at > STALE_MS)) render(stored);
  else send("capture");
})();
