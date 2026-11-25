const test = require("node:test");
const assert = require("node:assert");
const { describeFailure } = require("../addon/errors.js");

const f = (status, detail, retryAfter) => describeFailure({ status, detail, retryAfter });

test("401 asks to fix the key in options", () =>
  assert.deepStrictEqual(f(401), { error: "Clé API refusée", action: "options" }));

test("503 Quota exhausted shows Retry-After (seconds) in minutes, rounded up", () => {
  assert.deepStrictEqual(f(503, "Quota exhausted", "90"), { error: "Quota OpenRouter épuisé, réessayer dans 2 min" });
  assert.match(f(503, "Quota exhausted", "30").error, /dans 1 min/);
});

test("quota without a usable Retry-After still reads sensibly", () =>
  assert.deepStrictEqual(f(503, "Quota exhausted", null), { error: "Quota OpenRouter épuisé, réessayer plus tard" }));

test("502 and other 503 are retryable with the detail", () => {
  assert.deepStrictEqual(f(502, "OpenRouter returned 500"), { error: "Service indisponible : OpenRouter returned 500", action: "retry" });
  assert.deepStrictEqual(f(503, "boom"), { error: "Service indisponible : boom", action: "retry" });
});

test("422 shows the backend detail, no action", () => {
  assert.deepStrictEqual(f(422, "Capture required"), { error: "Capture required" });
  assert.deepStrictEqual(f(422, [{ msg: "x" }]), { error: "Erreur 422" });
});

test("unknown status falls back to a generic message", () =>
  assert.deepStrictEqual(f(500), { error: "Erreur 500" }));
