// Non-persistent background: does the whole click flow so it survives the popup closing.

async function setResult(tabId, result) {
  await browser.storage.session.set({ [`result:${tabId}`]: result });
  await browser.action.setBadgeText({ tabId, text: result.status === "ok" ? "✓" : result.status === "pending" ? "…" : "!" });
}

const fail = (error, action) => ({ status: "error", error, action });

// Files injected per extractor (in order; the last one must evaluate to a clonable object).
const EXTRACTOR_FILES = {
  readability: ["vendor/Readability.js", "extractors/readability.js"],
  academic: ["extractors/academic.js"],
  youtube: ["extractors/youtube.js"], // ends with a Promise: executeScript awaits it
};

const inject = async (tabId, files) => (await browser.scripting.executeScript({ target: { tabId }, files }))[0].result;

// -> payload fields, or {fail} (about:, PDF viewer, reader mode, AMO refuse injection)
async function extract(tabId, url) {
  try {
    const hasCitationAbstract = (await browser.scripting.executeScript({
      target: { tabId },
      func: () => !!document.querySelector('meta[name="citation_abstract"]'),
    }))[0].result;
    const decision = route(url, { hasCitationAbstract });
    const r = await inject(tabId, EXTRACTOR_FILES[decision.extractor]);
    if (r.notLoaded) return { fail: fail("Page pas encore chargée, réessayer", "reextract") };
    if (!r.full_text?.trim()) return { fail: fail("Aucun texte extrait") };
    return { payload: { title: r.title, full_text: r.full_text, ...(r.published_at && { published_at: r.published_at }) }, warnings: r.warnings };
  } catch {
    return { fail: fail("Page non capturable") };
  }
}

async function send(tabId, url) {
  await setResult(tabId, { status: "pending", step: "extraction", at: Date.now() });
  const { backendUrl, apiKey } = await browser.storage.local.get(["backendUrl", "apiKey"]);
  if (!backendUrl || !apiKey || !(await browser.permissions.contains({ origins: [hostPattern(backendUrl)] })))
    return fail("Configurer l'extension", "options");

  const decision = route(url);
  if (decision.action === "refuse") return fail(decision.reason);
  let extra = {}, warnings = [];
  if (decision.action === "extract") {
    const e = await extract(tabId, url);
    if (e.fail) return e.fail;
    extra = e.payload;
    warnings = e.warnings || [];
  }

  await setResult(tabId, { status: "pending", step: "envoi", at: Date.now() });
  return post(tabId, { url, ...extra }, warnings);
}

// Stores the payload (and its extraction warnings) so Retry can resend it without re-extracting.
async function post(tabId, payload, warnings = []) {
  await browser.storage.session.set({ [`payload:${tabId}`]: { payload, warnings } });
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
  return { status: "ok", created: resp.status === 201, source: await resp.json(), warnings };
}

// Any thrown error becomes an error result: the badge never stays on "…".
const guard = async (tabId, run) => {
  try { await setResult(tabId, await run()); }
  catch { await setResult(tabId, fail("Erreur inattendue")); }
};

// The popup sends only the tab id: the URL is read here so it is never stale.
const capture = (tabId) => guard(tabId, async () => send(tabId, (await browser.tabs.get(tabId)).url));

const retry = (tabId) => guard(tabId, async () => {
  const key = `payload:${tabId}`;
  const stored = (await browser.storage.session.get(key))[key];
  if (!stored) return send(tabId, (await browser.tabs.get(tabId)).url);
  await setResult(tabId, { status: "pending", step: "envoi", at: Date.now() });
  return post(tabId, stored.payload, stored.warnings);
});

// A new page in the tab invalidates its stored result.
browser.tabs.onUpdated.addListener((tabId) => {
  browser.storage.session.remove([`result:${tabId}`, `payload:${tabId}`]);
  browser.action.setBadgeText({ tabId, text: "" });
}, { properties: ["url"] });

browser.runtime.onMessage.addListener((msg) => {
  if (msg.type === "retry") retry(msg.tabId);
  if (msg.type === "capture") capture(msg.tabId); // no await: the reply is read from storage
});
