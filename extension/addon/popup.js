let tabId;
const root = document.getElementById("root");
const el = (tag, text, cls) => Object.assign(document.createElement(tag), { textContent: text, className: cls || "" });

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
    if (r.action === "retry") {
      const b = el("button", "Réessayer");
      b.onclick = () => browser.runtime.sendMessage({ type: "retry", tab: { id: tabId } });
      root.append(b);
    }
    return;
  }
  const s = r.source;
  root.append(el("h2", r.created ? "Ajoutée" : "Mise à jour"), el("strong", s.title || s.url), el("p", s.origin_site, "muted"), el("p", s.summary || ""));
  if (s.keywords?.length) root.append(el("p", s.keywords.join(", "), "muted"));
}

(async () => {
  const [tab] = await browser.tabs.query({ active: true, currentWindow: true });
  tabId = tab.id;
  const key = `result:${tab.id}`;
  browser.storage.onChanged.addListener((ch) => ch[key] && render(ch[key].newValue));
  // Reopening shows the last result; a new send happens only when none is stored (shortcut: no resend button yet).
  const stored = (await browser.storage.session.get(key))[key];
  if (stored) render(stored);
  else browser.runtime.sendMessage({ type: "capture", tab: { id: tab.id, url: tab.url } });
})();
