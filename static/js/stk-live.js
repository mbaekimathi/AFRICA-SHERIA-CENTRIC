(function () {
  var monitor = document.getElementById("stk-live-monitor");
  if (!monitor || !monitor.hasAttribute("data-stk-live") || !window.SheriaLivePoll) {
    return;
  }

  var pollUrl = monitor.getAttribute("data-poll-url");
  var initialStatus = monitor.getAttribute("data-status") || "pending";
  if (!pollUrl || (initialStatus !== "pending" && initialStatus !== "")) {
    return;
  }

  var successBanner = monitor.querySelector(".pay-stk-banner--success");
  var failedBanner = monitor.querySelector(".pay-stk-banner--failed");
  var pendingBanner = monitor.querySelector(".pay-stk-banner--pending");
  var liveLabel = monitor.querySelector(".js-stk-live-label");
  var receiptEl = monitor.querySelector(".js-stk-receipt");
  var invoiceStatusEl = monitor.querySelector(".js-stk-invoice-status");
  var failReasonEl = monitor.querySelector(".js-stk-fail-reason");
  var stopPoll = null;
  var reloaded = false;

  function hideAllBanners() {
    [successBanner, failedBanner, pendingBanner].forEach(function (el) {
      if (el) el.hidden = true;
    });
  }

  function applyStatus(data) {
    var status = (data && data.status) || "pending";
    monitor.className = "pay-stk-status pay-stk-status--" + status;

    if (status === "success") {
      hideAllBanners();
      if (successBanner) {
        successBanner.hidden = false;
        if (receiptEl && data.mpesa_receipt) {
          receiptEl.textContent = data.mpesa_receipt;
        }
        if (invoiceStatusEl && data.invoice_status_label) {
          invoiceStatusEl.textContent = data.invoice_status_label;
        }
      }
      if (stopPoll) stopPoll();
      if (!reloaded) {
        reloaded = true;
        window.setTimeout(function () {
          window.location.reload();
        }, 1200);
      }
      return true;
    }

    if (status === "failed" || status === "error") {
      hideAllBanners();
      if (failedBanner) {
        failedBanner.hidden = false;
        if (failReasonEl && data.result_desc) {
          failReasonEl.textContent = ": " + data.result_desc;
        }
      }
      if (stopPoll) stopPoll();
      return true;
    }

    if (pendingBanner) pendingBanner.hidden = false;
    if (liveLabel) {
      liveLabel.textContent =
        data.result_desc ||
        "Checking payment status live — enter your M-Pesa PIN on your phone.";
    }
    return false;
  }

  stopPoll = window.SheriaLivePoll.start({
    url: pollUrl,
    minMs: 3000,
    maxMs: 10000,
    factor: 1.25,
    onPayload: applyStatus,
  });
})();
