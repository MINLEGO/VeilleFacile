// Pure mapping: failed backend response -> popup {error, action}. Classic script in the extension, require() in tests.
function describeFailure({ status, detail, retryAfter }) {
  const text = typeof detail === "string" ? detail : "";
  if (status === 401) return { error: "Clé API refusée", action: "options" };
  if (status === 503 && text === "Quota exhausted") {
    const secs = Number(retryAfter);
    return { error: secs > 0 ? `Quota OpenRouter épuisé, réessayer dans ${Math.ceil(secs / 60)} min` : "Quota OpenRouter épuisé, réessayer plus tard" };
  }
  if (status === 502 || status === 503) return { error: `Service indisponible : ${text || status}`, action: "retry" };
  if (status === 422 && text) return { error: text };
  return { error: `Erreur ${status}` };
}

if (typeof module !== "undefined") module.exports = { describeFailure };
