/**
 * Fallback tracker page: open document window, stop when that window closes.
 */
(function () {
  var root = document.querySelector("[data-docs-session]");
  if (!root) return;

  var pingUrl = root.getAttribute("data-ping-url");
  var targetUrl = root.getAttribute("data-target-url");
  var libraryUrl = root.getAttribute("data-library-url");
  var timerEl = root.querySelector("[data-docs-session-timer]");
  var statusEl = root.querySelector("[data-docs-session-status]");
  var kindLabelEl = root.querySelector("[data-docs-session-kind-label]");
  var openBtn = root.querySelector("[data-docs-session-open]");
  var endBtn = root.querySelector("[data-docs-session-end]");
  var csrfInput = root.querySelector("[name=csrfmiddlewaretoken]");
  var csrfToken = csrfInput ? csrfInput.value : "";

  var startedAt = Date.now();
  var ended = false;
  var pingTimer = null;
  var clockTimer = null;
  var closeTimer = null;
  var docWindow = null;

  var KIND_LABELS = {
    viewing: "Viewing",
    editing: "Editing",
    creating: "Creating",
  };

  function formatDuration(totalSeconds) {
    var total = Math.max(0, Math.floor(totalSeconds || 0));
    var hours = Math.floor(total / 3600);
    var minutes = Math.floor((total % 3600) / 60);
    var seconds = total % 60;
    if (hours) {
      return hours + "h " + String(minutes).padStart(2, "0") + "m";
    }
    if (minutes) {
      return minutes + "m " + String(seconds).padStart(2, "0") + "s";
    }
    return seconds + "s";
  }

  function updateClock() {
    if (!timerEl || ended) return;
    var elapsed = Math.floor((Date.now() - startedAt) / 1000);
    timerEl.textContent = formatDuration(elapsed);
  }

  function setKindLabel(kind) {
    if (!kindLabelEl) return;
    kindLabelEl.textContent = KIND_LABELS[kind] || "Viewing";
  }

  function postAction(action, reason, syncContent) {
    if (!pingUrl || !csrfToken) return Promise.resolve(null);
    var body = new URLSearchParams();
    body.set("csrfmiddlewaretoken", csrfToken);
    body.set("action", action || "ping");
    if (reason) body.set("reason", reason);
    if (syncContent) body.set("sync_content", "1");
    return fetch(pingUrl, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
        "X-CSRFToken": csrfToken,
      },
      body: body.toString(),
      keepalive: action === "end",
    })
      .then(function (response) {
        return response.json().catch(function () {
          return null;
        });
      })
      .catch(function () {
        return null;
      });
  }

  function clearTimers() {
    if (pingTimer) clearInterval(pingTimer);
    if (clockTimer) clearInterval(clockTimer);
    if (closeTimer) clearInterval(closeTimer);
    pingTimer = null;
    clockTimer = null;
    closeTimer = null;
  }

  function endSession(reason, navigateAway) {
    if (ended) return;
    ended = true;
    clearTimers();
    if (statusEl) {
      statusEl.textContent = "Document closed — saving time used…";
    }
    postAction("end", reason || "window_closed", true).then(function (payload) {
      if (timerEl && payload && typeof payload.duration_seconds === "number") {
        timerEl.textContent = formatDuration(payload.duration_seconds);
      }
      if (payload && payload.kind) setKindLabel(payload.kind);
      if (statusEl) statusEl.textContent = "Session stopped.";
      if (navigateAway && libraryUrl) {
        window.location.href = libraryUrl;
      }
    });
  }

  function watchDocumentWindow(win) {
    docWindow = win;
    if (closeTimer) clearInterval(closeTimer);
    closeTimer = setInterval(function () {
      if (ended) return;
      try {
        if (!docWindow || docWindow.closed) {
          endSession("window_closed", true);
        }
      } catch (err) {
        endSession("window_closed", true);
      }
    }, 700);
  }

  function openTarget() {
    if (!targetUrl) return null;
    // Do not use noopener — we need .closed to auto-stop tracking.
    var win = window.open(targetUrl, "_blank");
    if (win) {
      watchDocumentWindow(win);
      if (statusEl) {
        statusEl.textContent =
          "Document open. Tracking will stop when you close that window.";
      }
    } else if (statusEl) {
      statusEl.textContent =
        "Pop-up blocked — click Open document, then close that window to stop tracking.";
    }
    return win;
  }

  if (openBtn) {
    openBtn.addEventListener("click", function (event) {
      event.preventDefault();
      openTarget();
    });
  }

  if (endBtn) {
    endBtn.addEventListener("click", function () {
      try {
        if (docWindow && !docWindow.closed) docWindow.close();
      } catch (err) {}
      endSession("manual", true);
    });
  }

  window.addEventListener("pagehide", function () {
    if (!ended) endSession("pagehide", false);
  });

  document.addEventListener("visibilitychange", function () {
    if (!ended && document.visibilityState === "visible") {
      postAction("ping", null, true).then(function (payload) {
        if (payload && payload.kind) setKindLabel(payload.kind);
      });
    }
  });

  setKindLabel("viewing");
  openTarget();
  updateClock();
  clockTimer = setInterval(updateClock, 1000);
  pingTimer = setInterval(function () {
    if (ended) return;
    postAction("ping", null, true).then(function (payload) {
      if (payload && payload.kind) setKindLabel(payload.kind);
    });
  }, 20000);
})();
