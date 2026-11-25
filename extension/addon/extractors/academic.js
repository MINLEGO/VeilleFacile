// Injected via scripting.executeScript. Must end with a structured-clonable value (plain object).
function vfExtractAcademic(doc) {
  // YYYY[-/MM[-/DD]] -> YYYY-MM-DD (missing parts = 01), else null
  const isoDate = (d) => {
    const m = d?.match(/^(\d{4})(?:[-/](\d{1,2})(?:[-/](\d{1,2}))?)?$/);
    if (!m) return null;
    const [y, mo = "1", da = "1"] = m.slice(1);
    return +mo >= 1 && +mo <= 12 && +da >= 1 && +da <= 31 ? `${y}-${mo.padStart(2, "0")}-${da.padStart(2, "0")}` : null;
  };
  const meta = (name) => doc.querySelector(`meta[name="${name}"]`)?.getAttribute("content")?.trim() || null;
  const date = meta("citation_date");
  return {
    title: meta("citation_title") || doc.title,
    full_text: meta("citation_abstract") || "",
    published_at: isoDate(date), // null when unparseable: the backend 422s on non-ISO dates
    warnings: [],
  };
}
vfExtractAcademic(document);
