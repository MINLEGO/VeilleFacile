// Non-persistent background: does the whole click flow so it survives the popup closing.
const hostPattern = (backendUrl) => { const u = new URL(backendUrl); return `${u.protocol}//${u.hostname}/*`; };

async function setResult(tabId, result) {
  await browser.storage.session.set({ [`result:${tabId}`]: result });
  await browser.action.setBadgeText({ tabId, text: result.status === "ok" ? "✓" : result.status === "pending" ? "…" : "!" });
}

const fail = (error, action) => ({ status: "error", error, action });

async function send(tabId, url) {
  const { backendUrl, apiKey } = await browser.storage.local.get(["backendUrl", "apiKey"]);
  if (!backendUrl || !apiKey || !(await browser.permissions.contains({ origins: [hostPattern(backendUrl)] })))
    return fail("Configurer l'extension", "options");

  const decision = route(url);
  if (decision.action === "refuse") return fail(decision.reason);
  // shortcut: only URL-only routes are implemented (#33); extractors come with #34/#36.
  if (decision.action === "extract") return fail("Extracteur pas encore disponible");

  let resp;
  try {
    resp = await fetch(new URL("/api/sources", backendUrl), {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${apiKey}` },
      body: JSON.stringify({ url }),
    });
  } catch {
    return fail(`Backend injoignable à ${backendUrl}`);
  }
  if (!resp.ok) return fail(`Erreur ${resp.status}`); // shortcut: per-status messages and Retry come with #35
  return { status: "ok", created: resp.status === 201, source: await resp.json() };
}

async function capture(tab) {
  await setResult(tab.id, { status: "pending", step: "envoi" });
  await setResult(tab.id, await send(tab.id, tab.url));
}

// A new page in the tab invalidates its stored result.
browser.tabs.onUpdated.addListener((tabId) => {
  browser.storage.session.remove(`result:${tabId}`);
  browser.action.setBadgeText({ tabId, text: "" });
}, { properties: ["url"] });

browser.runtime.onMessage.addListener((msg) => {
  if (msg.type === "capture") capture(msg.tab); // no await: the reply is read from storage
});
