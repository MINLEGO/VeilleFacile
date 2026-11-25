// Pure routing: URL -> what to send. Loaded as a classic script in the extension and via require() in tests.
function route(url, { hasCitationAbstract = false } = {}) {
  const NOT_CAPTURABLE = { action: "refuse", reason: "Page non capturable" };
  let u;
  try { u = new URL(url); } catch { return NOT_CAPTURABLE; }
  if (!/^https?:$/.test(u.protocol) || u.hostname === "addons.mozilla.org") return NOT_CAPTURABLE;

  const host = u.hostname.replace(/^(www|m)\./, "");
  if (host === "github.com" || host === "huggingface.co") return { action: "url-only" };
  if (host === "youtube.com") {
    return u.pathname === "/watch"
      ? { action: "extract", extractor: "youtube" }
      : { action: "refuse", reason: "Page YouTube non prise en charge" };
  }
  return { action: "extract", extractor: hasCitationAbstract ? "academic" : "readability" };
}

if (typeof module !== "undefined") module.exports = { route };
