// Injected via scripting.executeScript. Must end with a structured-clonable value (plain object).
function vfExtractAcademic(doc) {
  const meta = (name) => doc.querySelector(`meta[name="${name}"]`)?.getAttribute("content")?.trim() || null;
  const date = meta("citation_date");
  return {
    title: meta("citation_title") || doc.title,
    full_text: meta("citation_abstract") || "",
    published_at: date ? date.replaceAll("/", "-") : null, // shortcut: only YYYY/MM/DD -> YYYY-MM-DD, other formats pass through
    warnings: [],
  };
}
vfExtractAcademic(document);
