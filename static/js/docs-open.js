/**
 * Open a document in a tracked window.
 * Tracking starts on open and stops automatically when the document window is closed.
 */
(function () {
  var active = null;

  function csrfToken() {
    var input = document.querySelector("[name=csrfmiddlewaretoken]");
    if (input && input.value) return input.value;
    var match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  function formatDuration(totalSeconds) {
    var total = Math.max(0, Math.floor(totalSeconds || 0));
    var hours = Math.floor(total / 3600);
    var minutes = Math.floor((total % 3600) / 60);
    var seconds = total % 60;
    if (hours) return hours + "h " + String(minutes).padStart(2, "0") + "m";
    if (minutes) return minutes + "m " + String(seconds).padStart(2, "0") + "s";
    return seconds + "s";
  }

  function ensureBanner() {
    var banner = document.querySelector("[data-docs-track-banner]");
    if (banner) return banner;
    banner = document.createElement("div");
    banner.className = "docs-track-banner";
    banner.setAttribute("data-docs-track-banner", "");
    banner.hidden = true;
    banner.innerHTML =
      '<div class="docs-track-banner__inner">' +
      '<div class="docs-track-banner__copy">' +
      '<strong data-docs-track-title>Document open</strong>' +
      '<span data-docs-track-status>Tracking… Close the document window to stop.</span>' +
      "</div>" +
      '<div class="docs-track-banner__meta">' +
      '<span data-docs-track-kind>Viewing</span>' +
      '<strong data-docs-track-timer>0s</strong>' +
      "</div>" +
      '<button type="button" class="btn btn--quiet btn--inline" data-docs-track-stop>Stop</button>' +
      "</div>";
    document.body.appendChild(banner);
    banner
      .querySelector("[data-docs-track-stop]")
      .addEventListener("click", function () {
        if (active) endActive("manual", false);
      });
    return banner;
  }

  function updateBanner(payload) {
    if (!active || !active.banner) return;
    active.banner.hidden = false;
    var titleEl = active.banner.querySelector("[data-docs-track-title]");
    var statusEl = active.banner.querySelector("[data-docs-track-status]");
    var kindEl = active.banner.querySelector("[data-docs-track-kind]");
    var timerEl = active.banner.querySelector("[data-docs-track-timer]");
    if (titleEl) titleEl.textContent = active.title || "Document open";
    if (statusEl) {
      statusEl.textContent =
        "Tracking… Close the document window to stop.";
    }
    if (kindEl && payload && payload.kind) {
      var labels = {
        viewing: "Viewing",
        editing: "Editing",
        creating: "Creating",
      };
      kindEl.textContent = labels[payload.kind] || "Viewing";
    }
    if (timerEl) {
      var elapsed = Math.floor((Date.now() - active.startedAt) / 1000);
      timerEl.textContent = formatDuration(elapsed);
    }
  }

  function postPing(action, reason, syncContent) {
    if (!active || !active.pingUrl) return Promise.resolve(null);
    var body = new URLSearchParams();
    body.set("csrfmiddlewaretoken", csrfToken());
    body.set("action", action || "ping");
    if (reason) body.set("reason", reason);
    if (syncContent) body.set("sync_content", "1");
    return fetch(active.pingUrl, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
        "X-CSRFToken": csrfToken(),
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
    if (!active) return;
    if (active.closeTimer) clearInterval(active.closeTimer);
    if (active.clockTimer) clearInterval(active.clockTimer);
    if (active.pingTimer) clearInterval(active.pingTimer);
    active.closeTimer = null;
    active.clockTimer = null;
    active.pingTimer = null;
  }

  function endActive(reason, reopenBlockedHint) {
    if (!active || active.ending) return;
    active.ending = true;
    clearTimers();
    var banner = active.banner;
    var statusEl = banner && banner.querySelector("[data-docs-track-status]");
    if (statusEl) statusEl.textContent = "Stopping…";
    postPing("end", reason || "window_closed", true).finally(function () {
      if (banner) banner.hidden = true;
      active = null;
      if (reopenBlockedHint) {
        window.alert(
          "Allow pop-ups for this site so the document can open in a tracked window."
        );
      }
    });
  }

  function startMonitoring(docWindow, meta) {
    if (active) endActive("replaced", false);
    active = {
      win: docWindow,
      pingUrl: meta.ping_url,
      title: meta.document_title || "Document",
      startedAt: Date.now(),
      banner: ensureBanner(),
      ending: false,
      closeTimer: null,
      clockTimer: null,
      pingTimer: null,
    };
    updateBanner({ kind: "viewing" });

    active.clockTimer = setInterval(function () {
      updateBanner(null);
    }, 1000);

    active.closeTimer = setInterval(function () {
      if (!active || active.ending) return;
      try {
        if (!active.win || active.win.closed) {
          endActive("window_closed", false);
        }
      } catch (err) {
        endActive("window_closed", false);
      }
    }, 700);

    active.pingTimer = setInterval(function () {
      if (!active || active.ending) return;
      postPing("ping", null, true).then(function (payload) {
        updateBanner(payload);
      });
    }, 20000);

    window.addEventListener("pagehide", function onHide() {
      if (active) endActive("pagehide", false);
      window.removeEventListener("pagehide", onHide);
    });
  }

  function openTracked(startUrl, fallbackTarget) {
    // Open immediately from the user click so the browser allows the pop-up.
    var docWindow = window.open("about:blank", "_blank");
    if (!docWindow) {
      window.location.href = startUrl;
      return;
    }

    var url = startUrl;
    url += url.indexOf("?") >= 0 ? "&" : "?";
    url += "format=json";

    fetch(url, {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (response) {
        if (!response.ok) throw new Error("Could not start session");
        return response.json();
      })
      .then(function (meta) {
        var target = (meta && meta.target_url) || fallbackTarget;
        if (!target) throw new Error("Missing document URL");
        docWindow.location.href = target;
        startMonitoring(docWindow, meta || {});
      })
      .catch(function () {
        try {
          docWindow.close();
        } catch (err) {}
        window.location.href = startUrl;
      });
  }

  document.addEventListener("click", function (event) {
    var link = event.target.closest("[data-docs-open-track]");
    if (!link) return;
    event.preventDefault();
    openTracked(
      link.getAttribute("href"),
      link.getAttribute("data-target-url") || ""
    );
  });
})();
