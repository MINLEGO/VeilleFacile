const test = require("node:test");
const assert = require("node:assert");
const { route } = require("../addon/routing.js");

const URL_ONLY = { action: "url-only" };
const extract = (extractor) => ({ action: "extract", extractor });
const refuse = (reason) => ({ action: "refuse", reason });

test("GitHub and Hugging Face are sent as URL only", () => {
  assert.deepStrictEqual(route("https://github.com/MINLEGO/VeilleFacile"), URL_ONLY);
  assert.deepStrictEqual(route("https://huggingface.co/google/gemma-2"), URL_ONLY);
  assert.deepStrictEqual(route("https://www.github.com/a/b"), URL_ONLY);
});

test("a lookalike host is not GitHub", () => {
  assert.deepStrictEqual(route("https://notgithub.com/a"), extract("readability"));
});

test("YouTube watch pages use the YouTube extractor", () => {
  assert.deepStrictEqual(route("https://www.youtube.com/watch?v=abc"), extract("youtube"));
  assert.deepStrictEqual(route("https://m.youtube.com/watch?v=abc"), extract("youtube"));
});

test("other YouTube pages are refused", () => {
  for (const u of [
    "https://www.youtube.com/shorts/abc",
    "https://www.youtube.com/playlist?list=x",
    "https://www.youtube.com/@chan",
    "https://www.youtube.com/",
  ]) assert.deepStrictEqual(route(u), refuse("Page YouTube non prise en charge"), u);
});

test("pages with citation_abstract use the academic extractor", () => {
  assert.deepStrictEqual(route("https://arxiv.org/abs/1706.03762", { hasCitationAbstract: true }), extract("academic"));
});

test("any other page uses Readability", () => {
  assert.deepStrictEqual(route("https://www.anthropic.com/research/x"), extract("readability"));
});

test("non-injectable pages are refused", () => {
  for (const u of ["about:debugging", "moz-extension://x/popup.html", "view-source:https://a.b", "https://addons.mozilla.org/fr/firefox/", "not a url"])
    assert.deepStrictEqual(route(u), refuse("Page non capturable"), u);
});
