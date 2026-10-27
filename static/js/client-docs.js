/* Client portal documents — client-side search filter. */
document.addEventListener("DOMContentLoaded", () => {
  const search = document.querySelector("[data-doc-search]");
  if (!search) return;
  const rows = [...document.querySelectorAll("[data-doc-row]")];
  const empty = document.querySelector("[data-doc-empty]");
  const count = document.querySelector("[data-doc-count]");

  const apply = () => {
    const query = search.value.trim().toLowerCase();
    let shown = 0;
    rows.forEach((row) => {
      const text = (row.getAttribute("data-doc-text") || "").toLowerCase();
      const match = !query || text.includes(query);
      row.hidden = !match;
      if (match) shown += 1;
    });
    if (empty) empty.hidden = shown > 0;
    if (count) {
      count.textContent = query ? `${shown} of ${rows.length}` : "";
    }
  };

  search.addEventListener("input", apply);
  apply();
});
