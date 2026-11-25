const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const { JSDOM } = require("jsdom");

const addon = path.join(__dirname, "..", "addon");
const read = (p) => fs.readFileSync(path.join(addon, p), "utf8");
const fixture = (n) => fs.readFileSync(path.join(__dirname, "fixtures", n), "utf8");

// Injects files like scripting.executeScript({files}): one shared global, result = last expression of the last file.
function inject(htmlName, files) {
  const { window } = new JSDOM(fixture(htmlName), { runScripts: "outside-only" });
  let result;
  for (const f of files) result = window.eval(read(f));
  // Round trip through JSON: fails on functions/DOM nodes, and gives a plain object to compare.
  return JSON.parse(JSON.stringify(result));
}
const readability = (n) => inject(n, ["vendor/Readability.js", "extractors/readability.js"]);
const academic = (n) => inject(n, ["extractors/academic.js"]);

test("Readability: paragraphs are separated, date from article:published_time", () => {
  const r = readability("anthropic.html");
  assert.match(r.full_text, /substance\.\n+Second paragraph/);
  assert.match(r.full_text, /Item one of a list\nItem two/);
  assert.doesNotMatch(r.full_text, /Footer/);
  assert.strictEqual(r.published_at, "2024-06-20T10:00:00.000Z");
  assert.deepStrictEqual(r.warnings, []);
});

test("Readability: falls back to itemprop=datePublished", () => {
  const r = readability("thinkingmachines.html");
  assert.strictEqual(r.published_at, "2025-09-26");
  assert.strictEqual(r.title, "Modular Manifolds");
});

test("Readability: page without text gives empty full_text and no date", () => {
  const r = readability("empty.html");
  assert.strictEqual(r.full_text, "");
  assert.ok(!r.published_at);
});

test("Academic: abstract only, citation_title, ISO date", () => {
  assert.deepStrictEqual(academic("arxiv.html"), {
    title: "Attention Is All You Need",
    full_text: "The dominant sequence transduction models are based on complex recurrent networks.",
    published_at: "2017-06-12",
    warnings: [],
  });
});

// YouTube: async extractor, injected like executeScript (a Promise as last value is awaited by Firefox).
async function youtube(name, { setup } = {}) {
  const { window } = new JSDOM(fixture(name), { url: "https://www.youtube.com/watch?v=abc123", runScripts: "outside-only" });
  window.VF_YT_TIMEOUT_MS = 300;
  const log = [];
  setup?.(window, log);
  return { r: JSON.parse(JSON.stringify(await window.eval(read("extractors/youtube.js")))), log };
}
// Simulates YouTube: clicking the transcript button renders segments (new + old structure); the close button is observed.
function withTranscript(window, log) {
  const d = window.document;
  d.querySelector("ytd-video-description-transcript-section-renderer button").addEventListener("click", () => {
    log.push("open");
    d.querySelector("ytd-engagement-panel-section-list-renderer").insertAdjacentHTML("beforeend",
      `<transcript-segment-view-model><span class="ytAttributedStringHost">Hello everyone</span><div>1 second</div></transcript-segment-view-model>` +
      `<ytd-transcript-segment-renderer><span class="segment-text">second line</span></ytd-transcript-segment-renderer>`);
  });
  d.querySelector("#visibility-button button").addEventListener("click", () => log.push("close"));
}

test("YouTube: opens panel, one segment per line (no time label), closes it, original title, uploadDate, no description", async () => {
  const { r, log } = await youtube("youtube-transcript.html", { setup: withTranscript });
  assert.deepStrictEqual(r, { title: "Original Title", full_text: "Hello everyone\nsecond line", published_at: "2025-02-05T08:00:00-08:00", warnings: [] });
  assert.deepStrictEqual(log, ["open", "close"]);
});

test("YouTube: no transcript button gives title only and a warning", async () => {
  const { r } = await youtube("youtube-no-transcript.html");
  assert.deepStrictEqual(r, { title: "Silent Video", full_text: "Silent Video", published_at: "2025-02-05", warnings: ["sans transcription"] });
});

test("YouTube: stale microdata -> h1 title and French date", async () => {
  const { r } = await youtube("youtube-stale-fr.html");
  assert.strictEqual(r.title, "Titre de la seconde vidéo");
  assert.strictEqual(r.published_at, "2025-02-05");
});

test("YouTube: stale microdata -> English date", async () => {
  assert.strictEqual((await youtube("youtube-stale-en.html")).r.published_at, "2025-02-05");
});

test("YouTube: unparsable date is omitted", async () => {
  const { r } = await youtube("youtube-stale-fr.html", { setup: (w) => { w.document.querySelector("#info").textContent = "5 febrero 2025"; } });
  assert.ok(!r.published_at);
});

test("YouTube: still on another video after the wait is 'not loaded', never 'sans transcription'", async () => {
  assert.deepStrictEqual((await youtube("youtube-loading.html")).r, { notLoaded: true });
});
