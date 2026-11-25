const $ = (id) => document.getElementById(id);
const say = (t) => ($("msg").textContent = t);

browser.storage.local.get(["backendUrl", "apiKey"]).then((c) => {
  $("url").value = c.backendUrl || "";
  $("key").value = c.apiKey || "";
});

$("save").onclick = async () => {
  try {
    const backendUrl = $("url").value.trim();
    await browser.storage.local.set({ backendUrl, apiKey: $("key").value.trim() });
    // must be called straight from the click handler
    say((await browser.permissions.request({ origins: [hostPattern(backendUrl)] })) ? "Enregistré." : "Enregistré, mais permission d'hôte refusée.");
  } catch { say("URL invalide."); }
};

$("test").onclick = async () => {
  const { backendUrl, apiKey } = await browser.storage.local.get(["backendUrl", "apiKey"]);
  try {
    if (!backendUrl || !(await browser.permissions.contains({ origins: [hostPattern(backendUrl)] }))) return say("Permission absente : enregistrez d'abord.");
    const r = await fetch(new URL("/api/sources?limit=1", backendUrl), { headers: { Authorization: `Bearer ${apiKey}` } });
    say(r.ok ? "OK" : r.status === 401 ? "Clé refusée" : `Erreur ${r.status}`);
  } catch { say("URL invalide ou backend injoignable"); }
};
