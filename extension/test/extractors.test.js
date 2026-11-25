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
