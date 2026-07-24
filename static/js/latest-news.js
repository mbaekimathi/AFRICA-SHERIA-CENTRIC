(function () {
  var form = document.querySelector("[data-news-search]");
  var overlay = document.getElementById("news-search-overlay");
  if (!overlay) return;

  var title = document.getElementById("news-search-progress-title");
  var label = document.getElementById("news-search-progress-label");
  var percent = document.getElementById("news-search-progress-percent");
  var bar = document.getElementById("news-search-progress-bar");
  var track = overlay.querySelector("[role='progressbar']");
  var cancelButton = document.getElementById("news-search-cancel");
  var error = document.getElementById("news-search-error");
  var searchSubmit = form ? form.querySelector("button[type='submit']") : null;
  var csrfInput = form
    ? form.querySelector("input[name='csrfmiddlewaretoken']")
    : document.querySelector("input[name='csrfmiddlewaretoken']");
  var pollTimer = null;
  var statusUrl = "";
  var cancelUrl = "";
  var cancelPending = false;
  var terminal = false;
  var mode = "search";
  var activeWatchButton = null;

  function csrfToken() {
    return csrfInput ? csrfInput.value : "";
  }

  function updateProgress(value, text) {
    var safeValue = Math.max(0, Math.min(100, Number(value) || 0));
    bar.style.width = safeValue + "%";
    percent.textContent = safeValue + "%";
    track.setAttribute("aria-valuenow", String(safeValue));
    if (text) label.textContent = text;
  }

  function stopPolling() {
    if (pollTimer !== null) {
      window.clearTimeout(pollTimer);
      pollTimer = null;
    }
  }

  function resetControls() {
    if (searchSubmit) searchSubmit.disabled = false;
    if (form) form.removeAttribute("aria-busy");
    if (activeWatchButton) {
      activeWatchButton.disabled = false;
      activeWatchButton = null;
    }
    document.querySelectorAll("[data-news-watch-check] button").forEach(function (button) {
      button.disabled = false;
    });
  }

  function configureOverlay(nextMode, heading) {
    mode = nextMode;
    title.textContent = heading;
    cancelButton.textContent =
      nextMode === "watch" ? "Cancel check" : "Cancel search";
  }

  function showError(message) {
    terminal = true;
    stopPolling();
    error.textContent =
      message ||
      (mode === "watch"
        ? "The watch could not be checked."
        : "The news search could not be completed.");
    error.hidden = false;
    label.textContent = mode === "watch" ? "Check stopped" : "Search stopped";
    cancelButton.textContent = "Close";
    resetControls();
  }

  function schedulePoll() {
    stopPolling();
    pollTimer = window.setTimeout(pollStatus, 700);
  }

  async function pollStatus() {
    if (!statusUrl || terminal) return;
    try {
      var response = await fetch(statusUrl, {
        headers: { Accept: "application/json" },
        credentials: "same-origin",
      });
      if (!response.ok) throw new Error("Unable to read progress.");
      var data = await response.json();
      updateProgress(data.progress, data.label);

      if (data.status === "succeeded" && data.result_url) {
        terminal = true;
        updateProgress(
          100,
          data.label ||
            (mode === "watch"
              ? "Check complete — opening results"
              : "Search complete — opening results")
        );
        window.setTimeout(function () {
          window.location.assign(data.result_url);
        }, 450);
        return;
      }
      if (data.status === "cancelled") {
        terminal = true;
        label.textContent =
          data.label || (mode === "watch" ? "Check cancelled" : "Search cancelled");
        resetControls();
        window.setTimeout(function () {
          overlay.hidden = true;
        }, 600);
        return;
      }
      if (data.status === "failed") {
        showError(data.error);
        return;
      }
      schedulePoll();
    } catch (pollError) {
      showError(pollError.message);
    }
  }

  async function cancelCurrent() {
    if (terminal) {
      overlay.hidden = true;
      error.hidden = true;
      cancelButton.textContent =
        mode === "watch" ? "Cancel check" : "Cancel search";
      return;
    }
    cancelPending = true;
    cancelButton.disabled = true;
    label.textContent =
      mode === "watch" ? "Cancelling check…" : "Cancelling search…";
    stopPolling();
    if (!cancelUrl) return;
    try {
      var response = await fetch(cancelUrl, {
        method: "POST",
        headers: {
          Accept: "application/json",
          "X-CSRFToken": csrfToken(),
        },
        credentials: "same-origin",
      });
      if (!response.ok) throw new Error("The operation could not be cancelled.");
      var data = await response.json();
      terminal = true;
      updateProgress(
        data.progress,
        data.label || (mode === "watch" ? "Check cancelled" : "Search cancelled")
      );
      resetControls();
      window.setTimeout(function () {
        overlay.hidden = true;
        cancelButton.disabled = false;
      }, 600);
    } catch (cancelError) {
      cancelButton.disabled = false;
      showError(cancelError.message);
    }
  }

  function beginOverlay(nextMode, heading, startingLabel) {
    stopPolling();
    statusUrl = "";
    cancelUrl = "";
    cancelPending = false;
    terminal = false;
    error.hidden = true;
    cancelButton.disabled = false;
    configureOverlay(nextMode, heading);
    updateProgress(0, startingLabel);
    overlay.hidden = false;
  }

  if (form) {
    form.addEventListener("submit", async function (event) {
      event.preventDefault();
      if (form.getAttribute("aria-busy") === "true") return;

      beginOverlay(
        "search",
        "Searching and analysing articles",
        "Submitting search filters…"
      );
      if (searchSubmit) searchSubmit.disabled = true;
      form.setAttribute("aria-busy", "true");

      try {
        var response = await fetch(form.action, {
          method: "POST",
          body: new FormData(form),
          headers: { Accept: "application/json" },
          credentials: "same-origin",
        });
        var data = await response.json();
        if (!response.ok) {
          var message = "Check the search filters and try again.";
          if (data.errors) {
            var field = Object.keys(data.errors)[0];
            if (field && data.errors[field][0]) {
              message = data.errors[field][0].message;
            }
          }
          throw new Error(message);
        }
        statusUrl = data.status_url;
        cancelUrl = data.cancel_url;
        updateProgress(1, "Search queued");
        if (cancelPending) {
          await cancelCurrent();
        } else {
          schedulePoll();
        }
      } catch (startError) {
        showError(startError.message);
      }
    });
  }

  document.querySelectorAll("[data-news-watch-check]").forEach(function (watchForm) {
    watchForm.addEventListener("submit", async function (event) {
      event.preventDefault();
      if (overlay.hidden === false && !terminal) return;

      var watchName = watchForm.getAttribute("data-watch-name") || "this watch";
      var submitButton = watchForm.querySelector("button[type='submit']");
      activeWatchButton = submitButton;
      if (submitButton) submitButton.disabled = true;
      document.querySelectorAll("[data-news-watch-check] button").forEach(function (button) {
        button.disabled = true;
      });

      beginOverlay(
        "watch",
        "Checking monitored news",
        "Starting check for “" + watchName + "”…"
      );

      try {
        var response = await fetch(watchForm.action, {
          method: "POST",
          body: new FormData(watchForm),
          headers: { Accept: "application/json" },
          credentials: "same-origin",
        });
        var data = await response.json();
        if (response.status === 409) {
          throw new Error(data.message || "This watch is already being checked.");
        }
        if (!response.ok) {
          throw new Error(data.message || "The watch could not be checked.");
        }
        statusUrl = data.status_url;
        cancelUrl = data.cancel_url;
        updateProgress(1, "Watch check queued");
        if (cancelPending) {
          await cancelCurrent();
        } else {
          schedulePoll();
        }
      } catch (startError) {
        showError(startError.message);
      }
    });
  });

  cancelButton.addEventListener("click", cancelCurrent);

  var focusedArticle = document.getElementById("news-article-focus");
  if (focusedArticle && typeof focusedArticle.scrollIntoView === "function") {
    window.setTimeout(function () {
      focusedArticle.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 120);
  }
})();
