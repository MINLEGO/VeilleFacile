// Injected after vendor/Readability.js. Must end with a structured-clonable value (plain object).
function vfExtractReadability(doc) {
  const parsed = new Readability(doc.cloneNode(true)).parse();
  // textContent glues paragraphs together: add a newline after each block element first.
  const div = doc.createElement("div");
  div.innerHTML = parsed?.content || "";
  div.querySelectorAll("p,h1,h2,h3,h4,h5,h6,li,pre,blockquote,tr,div,br,figcaption").forEach((el) => el.after("\n"));
  const full_text = div.textContent
    .replace(/[ \t]+/g, " ")
    .replace(/ ?\n ?/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
  const itemprop = doc.querySelector('meta[itemprop="datePublished"]')?.getAttribute("content");
  return {
    title: parsed?.title || doc.title,
    full_text,
    published_at: parsed?.publishedTime || itemprop || null,
    warnings: [],
  };
}
vfExtractReadability(document);
