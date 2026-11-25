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

  return post(tabId, { url });
}

// Stores the payload so Retry can resend it without re-extracting.
async function post(tabId, payload) {
  await browser.storage.session.set({ [`payload:${tabId}`]: payload });
  const { backendUrl, apiKey } = await browser.storage.local.get(["backendUrl", "apiKey"]);
  let resp;
  try {
    resp = await fetch(new URL("/api/sources", backendUrl), {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${apiKey}` },
      body: JSON.stringify(payload),
    });
  } catch {
    return fail(`Backend injoignable à ${backendUrl}`, "retry");
  }
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    return { status: "error", ...describeFailure({ status: resp.status, detail: body.detail, retryAfter: resp.headers.get("Retry-After") }) };
  }
  return { status: "ok", created: resp.status === 201, source: await resp.json() };
}

async function capture(tab) {
  await setResult(tab.id, { status: "pending", step: "envoi" });
  await setResult(tab.id, await send(tab.id, tab.url));
}

async function retry(tabId) {
  const key = `payload:${tabId}`;
  const payload = (await browser.storage.session.get(key))[key];
  await setResult(tabId, { status: "pending", step: "envoi" });
  await setResult(tabId, await post(tabId, payload));
}

// A new page in the tab invalidates its stored result.
browser.tabs.onUpdated.addListener((tabId) => {
  browser.storage.session.remove([`result:${tabId}`, `payload:${tabId}`]);
  browser.action.setBadgeText({ tabId, text: "" });
}, { properties: ["url"] });

browser.runtime.onMessage.addListener((msg) => {
  if (msg.type === "retry") retry(msg.tab.id);
  if (msg.type === "capture") capture(msg.tab); // no await: the reply is read from storage
});
