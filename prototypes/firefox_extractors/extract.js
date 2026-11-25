// PROTOTYPE, throwaway (map #26, ticket #28). Not the real extractor.
// Injected into the tab; window.__vfExtract() returns {title, full_text, published_at, debug}.

window.__vfExtract = async function () {
  const clean = (s) => (s || "").replace(/[ \t]+/g, " ").replace(/\n\s*\n\s*\n+/g, "\n\n").trim();
  const meta = (sel) => document.querySelector(sel)?.getAttribute("content") || null;
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  async function waitFor(fn, ms) {
    const end = Date.now() + ms;
    while (Date.now() < end) {
      const v = fn();
      if (v) return v;
      await sleep(100);
    }
    return null;
  }

  async function youtube() {
    const debug = { kind: "youtube" };
    const videoId = new URLSearchParams(location.search).get("v");

    // SPA: after in-site navigation the microdata/<meta> still describe the FIRST video loaded.
    const microId = document.querySelector('meta[itemprop="identifier"]')?.content || null;
    debug.microdata_fresh = microId === videoId;

    // h1 / document.title are auto-translated to the UI language; meta[name=title] is the original.
    debug.title_h1 = document.querySelector("ytd-watch-metadata h1")?.innerText?.trim() || null;
    debug.title_meta = meta('meta[name="title"]');
    const title = (debug.microdata_fresh && debug.title_meta) || debug.title_h1 || document.title.replace(/ - YouTube$/, "");

    // Upload date candidates
    debug.date_candidates = {
      itemprop_uploadDate: meta('meta[itemprop="uploadDate"]'),
      itemprop_datePublished: meta('meta[itemprop="datePublished"]'),
      jsonld: (() => {
        for (const s of document.querySelectorAll('script[type="application/ld+json"]')) {
          try {
            const j = JSON.parse(s.textContent);
            if (j.uploadDate) return j.uploadDate;
          } catch {}
        }
        return null;
      })(),
      info_text: document.querySelector("#info-container #info, ytd-watch-info-text #info")?.innerText || null,
    };

    // Description (expand it first so we don't read the truncated snippet)
    document.querySelector("#description-inline-expander #expand, tp-yt-paper-button#expand")?.click();
    await sleep(300);
    const description = clean(
      document.querySelector("#description-inline-expander yt-attributed-string, #description-inline-expander")
        ?.innerText
    );

    // Transcript panel (selectors from docs/research/youtube-transcript-capture.md)
    const SEG = "transcript-segment-view-model, ytd-transcript-segment-renderer";
    let segs = document.querySelectorAll(SEG);
    let opened = false;
    if (!segs.length) {
      const btnSelectors = [
        "ytd-video-description-transcript-section-renderer button",
        'button[aria-label="Show transcript"]',
        'button[aria-label="Afficher la transcription"]',
        'button[aria-label="Transcript"]',
        'button[aria-label="Transcription"]',
      ];
      const btn = btnSelectors.map((s) => document.querySelector(s)).find(Boolean);
      debug.transcript_button = btn ? btnSelectors.find((s) => document.querySelector(s)) : null;
      if (btn) {
        btn.click();
        opened = true;
        await waitFor(() => document.querySelectorAll(SEG).length, 5000);
        segs = document.querySelectorAll(SEG);
      }
    }
    debug.segment_count = segs.length;
    debug.segment_tag = segs[0]?.tagName?.toLowerCase() || null;

    const transcript = clean(
      [...segs]
        .map((s) => {
          const t = s.querySelector(".segment-text, span.ytAttributedStringHost, .yt-core-attributed-string, yt-formatted-string");
          return (t || s).innerText.replace(/^\s*\d+:\d+(:\d+)?\s*/, "").trim();
        })
        .filter(Boolean)
        .join("\n")
    );

    if (opened) {
      document
        .querySelector(
          'ytd-engagement-panel-section-list-renderer[target-id*="transcript"] #visibility-button button, ' +
            'ytd-engagement-panel-section-list-renderer[target-id*="transcript"] button[aria-label="Close transcript"]'
        )
        ?.click();
    }

    debug.has_transcript = !!transcript;
    return {
      title,
      full_text: transcript || [title, description].filter(Boolean).join("\n\n"),
      published_at: debug.microdata_fresh
        ? debug.date_candidates.itemprop_uploadDate || debug.date_candidates.itemprop_datePublished
        : null,
      debug: {
        ...debug,
        description_chars: description.length,
        // localized absolute date once the description is expanded, e.g. "10 974 174 vues  5 févr. 2025"
        info_expanded: document.querySelector("ytd-watch-info-text #info")?.innerText || null,
      },
    };
  }

  function article() {
    const debug = { kind: "readability" };
    const parsed = new Readability(document.cloneNode(true)).parse();
    debug.readability_published = parsed?.publishedTime || null;
    debug.date_candidates = {
      article_published_time: meta('meta[property="article:published_time"]'),
      itemprop_datePublished: meta('meta[itemprop="datePublished"]'),
      citation_date: meta('meta[name="citation_date"]'),
      citation_online_date: meta('meta[name="citation_online_date"]'),
      time_datetime: document.querySelector("time[datetime]")?.getAttribute("datetime") || null,
    };
    debug.byline = parsed?.byline || null;
    debug.site = parsed?.siteName || null;
    // textContent glues paragraphs together ("end.Next"): add a newline after each block first.
    const div = document.createElement("div");
    div.innerHTML = parsed?.content || "";
    div.querySelectorAll("p,h1,h2,h3,h4,h5,h6,li,pre,blockquote,tr,div,br,figcaption").forEach((el) => el.after("\n"));
    const readabilityText = clean(div.textContent);
    debug.textContent_chars = (parsed?.textContent || "").length;

    // Academic pages (arXiv /abs/, many publishers) expose the abstract in Highwire meta tags.
    const abstract = meta('meta[name="citation_abstract"]');
    debug.used = abstract ? "citation_abstract" : "readability";
    const date =
      parsed?.publishedTime ||
      debug.date_candidates.itemprop_datePublished ||
      debug.date_candidates.citation_date?.replaceAll("/", "-") ||
      null;
    return {
      title: meta('meta[name="citation_title"]') || parsed?.title || document.title,
      full_text: abstract ? clean(abstract) : readabilityText,
      published_at: date,
      debug,
    };
  }

  const t0 = performance.now();
  const isYt = /(^|\.)youtube\.com$/.test(location.hostname) && location.pathname === "/watch";
  const out = isYt ? await youtube() : article();
  out.debug.ms = Math.round(performance.now() - t0);
  out.url = location.href;
  return out;
};

// executeScript({files}) returns the last expression of the last file; a function is not clonable.
undefined;
