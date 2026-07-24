/**
 * Account-status live sync for every authenticated page.
 * Redirects when the signed-in account status changes (approval, suspend, etc.).
 */
document.addEventListener("DOMContentLoaded", () => {
  if (!window.SheriaLivePoll) return;

  const page =
    document.getElementById("client-pending-page") ||
    document.getElementById("employee-pending-page") ||
    document.getElementById("live-session-page");

  const statusUrl =
    (page && page.dataset.statusUrl) || document.body.dataset.liveStatusUrl;
  const expectedStatus =
    (page && page.dataset.expectedStatus) ||
    document.body.dataset.liveExpectedStatus;

  if (!statusUrl || !expectedStatus) return;

  window.SheriaLivePoll.start({
    url: statusUrl,
    minMs: 10000,
    maxMs: 60000,
    factor: 1.8,
    onPayload: (data) => {
      if (!data || !data.redirect_url) return false;
      if (data.status === expectedStatus) return false;
      window.location.assign(data.redirect_url);
      return true;
    },
  });
});
