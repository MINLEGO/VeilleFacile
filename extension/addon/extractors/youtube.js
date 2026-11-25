// Injected via scripting.executeScript on youtube.com/watch. Ends with a Promise (Firefox awaits it) of a plain object:
// {title, full_text, published_at, warnings} or {notLoaded: true}.
async function vfExtractYouTube(doc, timeoutMs) {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  async function waitFor(fn, ms) {
    for (const end = Date.now() + ms; Date.now() < end; await sleep(50)) { const v = fn(); if (v) return v; }
    return fn() || null;
  }
  const $ = (sel) => doc.querySelector(sel);
  const videoId = new URL(doc.location.href).searchParams.get("v");

  // Wait for the description section of THIS video (SPA navigation leaves the previous video's DOM for a while).
  const ready = await waitFor(() => $("#description-inline-expander") && $("ytd-watch-flexy")?.getAttribute("video-id") === videoId, timeoutMs);
  if (!ready) return { notLoaded: true };

  // After in-site navigation the meta tags describe the first video loaded.
  const fresh = $('meta[itemprop="identifier"]')?.content === videoId;
  const meta = (sel) => $(sel)?.getAttribute("content")?.trim() || null;
  const title = (fresh && meta('meta[name="title"]')) || $("ytd-watch-metadata h1")?.textContent.trim() || doc.title.replace(/ - YouTube$/, "");

  let published_at = null;
  if (fresh) published_at = meta('meta[itemprop="uploadDate"]');
  else {
    $("#description-inline-expander #expand")?.click();
    // shortcut: FR/EN month tables only; other UI languages omit the date
    const text = await waitFor(() => parseDisplayedDate($("ytd-watch-info-text #info")?.textContent || ""), 2000);
    published_at = text || null;
  }

  const SEG = "transcript-segment-view-model, ytd-transcript-segment-renderer";
  let opened = false;
  if (!doc.querySelector(SEG)) {
    const btn = [
      "ytd-video-description-transcript-section-renderer button",
      'button[aria-label="Show transcript"]',
      'button[aria-label="Afficher la transcription"]',
      'button[aria-label="Transcript"]',
    ].map($).find(Boolean);
    if (btn) { btn.click(); opened = true; await waitFor(() => doc.querySelector(SEG), 5000); }
  }
  const lines = [...doc.querySelectorAll(SEG)]
    .map((s) => s.querySelector("span.ytAttributedStringHost, .segment-text")?.textContent.trim())
    .filter(Boolean);
  if (opened) $('ytd-engagement-panel-section-list-renderer[target-id*="transcript"] #visibility-button button')?.click();

  return lines.length
    ? { title, full_text: lines.join("\n"), published_at, warnings: [] }
    : { title, full_text: title, published_at, warnings: ["sans transcription"] }; // description is never sent
}

function parseDisplayedDate(s) {
  const M = {};
  [["jan", "janv", "janvier", "january"], ["feb", "févr", "février", "february"], ["mar", "mars", "march"], ["apr", "avr", "avril", "april"],
    ["may", "mai"], ["jun", "juin", "june"], ["jul", "juil", "juillet", "july"], ["aug", "août", "august"], ["sep", "sept", "septembre", "september"],
    ["oct", "octobre", "october"], ["nov", "novembre", "november"], ["dec", "déc", "décembre", "december"]]
    .forEach((names, i) => names.forEach((n) => (M[n] = i + 1)));
  const pick = (name) => M[name.toLowerCase().replace(/\.$/, "")];
  const fr = s.match(/(\d{1,2})\s+([^\s\d,]+?)\.?\s+(\d{4})/); // "5 févr. 2025"
  const en = s.match(/([^\s\d,]+?)\.?\s+(\d{1,2}),\s+(\d{4})/); // "Feb 5, 2025"
  const [d, m, y] = fr ? [fr[1], pick(fr[2]), fr[3]] : en ? [en[2], pick(en[1]), en[3]] : [];
  return m ? `${y}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}` : null;
}

vfExtractYouTube(document, globalThis.VF_YT_TIMEOUT_MS ?? 10000);
