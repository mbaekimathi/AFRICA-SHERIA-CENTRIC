document.addEventListener("DOMContentLoaded", () => {
  const page = document.getElementById("live-list-page");
  if (!page) return;

  page.addEventListener("click", (event) => {
    const row = event.target.closest("tr.is-clickable-row");
    if (!row || !page.contains(row)) return;
    if (event.target.closest("a, button, input, label, select, textarea")) return;
    const href = row.dataset.href;
    if (!href) return;
    window.location.href = href;
  });

  if (!window.SheriaLivePoll) return;

  const revisionUrl = page.dataset.revisionUrl;
  if (!revisionUrl) return;

  let knownRevision = null;

  window.SheriaLivePoll.start({
    url: revisionUrl,
    minMs: 5000,
    maxMs: 30000,
    onPayload: (data) => {
      if (!data || typeof data.revision !== "string") return false;
      if (knownRevision === null) {
        knownRevision = data.revision;
        return false;
      }
      if (data.revision === knownRevision) return false;
      window.location.reload();
      return true;
    },
  });
});
