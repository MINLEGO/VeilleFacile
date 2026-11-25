// PROTOTYPE, throwaway (ticket #28).
const $ = (id) => document.getElementById(id);
(async () => {
  try {
    const [tab] = await browser.tabs.query({ active: true, currentWindow: true });
    const target = { tabId: tab.id };
    await browser.scripting.executeScript({ target, files: ["Readability.js", "extract.js"] });
    const [{ result: r }] = await browser.scripting.executeScript({ target, func: () => window.__vfExtract() });
    $("status").textContent = r.debug.kind === "youtube" && !r.debug.has_transcript
      ? "YouTube : sans transcription (titre + description)" : "OK";
    if (r.debug.kind === "youtube" && !r.debug.has_transcript) $("status").className = "warn";
    $("title").textContent = r.title || "(vide)";
    $("date").textContent = r.published_at || "(omis)";
    $("len").textContent = r.full_text.length;
    $("text").value = r.full_text;
    $("debug").textContent = JSON.stringify(r.debug, null, 2);
  } catch (e) {
    $("status").textContent = "Erreur : " + e.message;
    $("status").className = "warn";
  }
})();
