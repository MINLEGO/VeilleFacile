// Non-persistent background: does the whole click flow so it survives the popup closing.
const hostPattern = (backendUrl) => { const u = new URL(backendUrl); return `${u.protocol}//${u.hostname}/*`; };

async function setResult(tabId, result) {
  await browser.storage.session.set({ [`result:${tabId}`]: result });
  await browser.action.setBadgeText({ tabId, text: result.status === "ok" ? "✓" : result.status === "pending" ? "…" : "!" });
}

const fail = (error, action) => ({ status: "error", error, action });

// Files injected per extractor (in order; the last one must evaluate to a clonable object). YouTube (#36) adds its entry here.
const EXTRACTOR_FILES = {
  readability: ["vendor/Readability.js", "extractors/readability.js"],
  academic: ["extractors/academic.js"],
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
    if (!r.full_text?.trim()) return { fail: fail("Aucun texte extrait") };
    return { payload: { title: r.title, full_text: r.full_text, ...(r.published_at && { published_at: r.published_at }) } };
  } catch {
    return { fail: fail("Page non capturable") };
  }
}

async function send(tabId, url) {
  const { backendUrl, apiKey } = await browser.storage.local.get(["backendUrl", "apiKey"]);
  if (!backendUrl || !apiKey || !(await browser.permissions.contains({ origins: [hostPattern(backendUrl)] })))
    return fail("Configurer l'extension", "options");

  const decision = route(url);
  if (decision.action === "refuse") return fail(decision.reason);
  let extra = {};
  if (decision.action === "extract") {
    const e = await extract(tabId, url);
    if (e.fail) return e.fail;
    extra = e.payload;
  }

  return post(tabId, { url, ...extra });
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
