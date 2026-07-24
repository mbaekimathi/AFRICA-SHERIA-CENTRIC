/**
 * Watches a reviewed client/employee on approve & assist pages.
 * Leaves the page when their status changes elsewhere.
 */
document.addEventListener("DOMContentLoaded", () => {
  const page = document.getElementById("live-entity-page");
  if (!page || !window.SheriaLivePoll) return;

  const statusUrl = page.dataset.statusUrl;
  const expectedStatus = page.dataset.expectedStatus;
  const goneUrl = page.dataset.goneUrl;
  if (!statusUrl || !expectedStatus || !goneUrl) return;

  window.SheriaLivePoll.start({
    url: statusUrl,
    minMs: 8000,
    maxMs: 45000,
    factor: 1.7,
    onPayload: (data) => {
      if (!data) return false;
      if (data.exists === false || data.status !== expectedStatus) {
        window.location.assign(goneUrl);
        return true;
      }
      return false;
    },
  });
});
