(function () {
  var page = document.getElementById("communication-settings-page");
  if (!page) return;

  var verifyUrl = page.getAttribute("data-communication-verify-url");
  if (!verifyUrl) return;

  var form = document.getElementById("communication-settings-form");
  var list = page.querySelector(".js-comm-connections-list");
  var overallPill = page.querySelector(".js-comm-overall-pill");
  var overallDetail = page.querySelector(".js-comm-overall-detail");
  var verifiedAt = page.querySelector(".js-comm-verified-at");
  var btn = page.querySelector(".js-comm-verify-btn");
  var spinner = page.querySelector(".js-comm-verify-spinner");
  var btnLabel = page.querySelector(".js-comm-verify-label");
  var verifying = false;

  var FIELD_KEYS = [
    "email_enabled",
    "email_host",
    "email_port",
    "email_host_user",
    "email_host_password",
    "email_from_email",
    "email_from_name",
    "sms_enabled",
    "sms_provider",
    "sms_username",
    "sms_api_key",
    "sms_api_secret",
    "sms_sender_id",
    "whatsapp_enabled",
    "whatsapp_business_number",
    "whatsapp_default_message",
    "whatsapp_api_enabled",
    "whatsapp_provider",
    "whatsapp_api_token",
    "whatsapp_phone_number_id",
    "whatsapp_webhook_url",
  ];

  var BOOL_KEYS = {
    email_enabled: true,
    sms_enabled: true,
    whatsapp_enabled: true,
    whatsapp_api_enabled: true,
  };

  var PANEL_IDS = {
    email: "communication-email-panel",
    sms: "communication-sms-panel",
    whatsapp: "communication-whatsapp-panel",
  };

  function csrfToken() {
    var input = form
      ? form.querySelector("[name=csrfmiddlewaretoken]")
      : document.querySelector("[name=csrfmiddlewaretoken]");
    if (input && input.value) return input.value;
    var match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  function fieldInput(key) {
    return document.getElementById("id_" + key);
  }

  function fieldWrap(key) {
    var input = fieldInput(key);
    if (!input) return null;
    return input.closest(".form-field") || input.parentElement;
  }

  function collectValues() {
    var values = {};
    FIELD_KEYS.forEach(function (key) {
      var input = fieldInput(key);
      if (!input) {
        values[key] = BOOL_KEYS[key] ? false : "";
        return;
      }
      if (BOOL_KEYS[key]) {
        values[key] = !!input.checked;
      } else {
        values[key] = String(input.value || "").trim();
      }
    });
    return values;
  }

  function setBusy(busy) {
    verifying = busy;
    if (btn) btn.disabled = busy;
    if (spinner) spinner.hidden = !busy;
    if (btnLabel) {
      btnLabel.textContent = busy ? "Verifying…" : "Verify configuration";
    }
  }

  function escapeHtml(text) {
    return String(text || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function clearFieldProblems() {
    page.querySelectorAll(".form-field.is-problem").forEach(function (el) {
      el.classList.remove("is-problem");
    });
    page.querySelectorAll(".js-comm-live-error").forEach(function (el) {
      el.remove();
    });
    page.querySelectorAll(".panel.is-problem-panel").forEach(function (el) {
      el.classList.remove("is-problem-panel");
    });
  }

  function revealChannelPanel(channelKey) {
    var panel = document.getElementById(PANEL_IDS[channelKey] || "");
    if (!panel) return;
    panel.hidden = false;
    panel.classList.add("is-problem-panel");
    if (channelKey === "whatsapp") {
      var apiFields = document.getElementById("communication-whatsapp-api-fields");
      var apiToggle = fieldInput("whatsapp_api_enabled");
      if (apiFields && apiToggle && apiToggle.checked) {
        apiFields.hidden = false;
      }
    }
  }

  function highlightProblems(data) {
    clearFieldProblems();
    var locations = Array.isArray(data.problem_locations)
      ? data.problem_locations
      : [];
    var firstFocus = null;

    locations.forEach(function (loc) {
      revealChannelPanel(loc.channel);
      var fields = Array.isArray(loc.fields) ? loc.fields : [];
      var message = loc.detail || loc.fix_hint || "This field needs attention.";
      fields.forEach(function (fieldKey, index) {
        var wrap = fieldWrap(fieldKey);
        var input = fieldInput(fieldKey);
        if (!wrap) return;
        wrap.classList.add("is-problem");
        var hint = document.createElement("p");
        hint.className = "field-error js-comm-live-error";
        hint.setAttribute("role", "alert");
        hint.textContent = index === 0 ? message : loc.fix_hint || message;
        wrap.appendChild(hint);
        if (!firstFocus && input) firstFocus = input;
      });
      if (!fields.length && !firstFocus) {
        var panel = document.getElementById(PANEL_IDS[loc.channel] || "");
        if (panel) firstFocus = panel;
      }
    });

    if (firstFocus && typeof firstFocus.scrollIntoView === "function") {
      window.setTimeout(function () {
        firstFocus.scrollIntoView({ behavior: "smooth", block: "center" });
        if (typeof firstFocus.focus === "function") {
          try {
            firstFocus.focus({ preventScroll: true });
          } catch (err) {
            firstFocus.focus();
          }
        }
      }, 80);
    }
  }

  function renderChannelItem(channel) {
    var valueHtml;
    if (channel.href && channel.value) {
      valueHtml =
        '<a class="contact-connections__value" href="' +
        escapeHtml(channel.href) +
        '" target="_blank" rel="noopener noreferrer">' +
        escapeHtml(channel.value) +
        "</a>";
    } else {
      valueHtml =
        '<span class="contact-connections__value">' +
        escapeHtml(channel.value || "—") +
        "</span>";
    }

    var isProblem =
      channel.status === "invalid" ||
      channel.status === "unreachable" ||
      channel.status === "not_set";
    var problemHtml = "";
    if (isProblem) {
      var where =
        Array.isArray(channel.problem_labels) && channel.problem_labels.length
          ? channel.problem_labels.join(", ")
          : "";
      problemHtml =
        '<p class="contact-connections__problem">' +
        '<strong>Problem:</strong> ' +
        escapeHtml(channel.detail || "Needs attention") +
        (where
          ? ' <span class="contact-connections__where">Where: ' +
            escapeHtml(where) +
            "</span>"
          : "") +
        (channel.fix_hint
          ? '<span class="contact-connections__fix">' +
            escapeHtml(channel.fix_hint) +
            "</span>"
          : "") +
        "</p>";
    }

    return (
      '<li class="contact-connections__item' +
      (isProblem ? " is-problem" : "") +
      '" data-channel-key="' +
      escapeHtml(channel.key) +
      '" data-status="' +
      escapeHtml(channel.status) +
      '">' +
      '<div class="contact-connections__item-main">' +
      '<span class="contact-connections__label">' +
      escapeHtml(channel.label) +
      "</span>" +
      valueHtml +
      problemHtml +
      "</div>" +
      '<div class="contact-connections__item-status">' +
      '<span class="status-pill status-pill--' +
      escapeHtml(channel.tone) +
      '">' +
      escapeHtml(channel.status_label) +
      "</span>" +
      '<span class="contact-connections__detail">' +
      escapeHtml(channel.detail) +
      "</span>" +
      "</div>" +
      "</li>"
    );
  }

  function updateFieldPills(byKey) {
    page.querySelectorAll(".js-comm-field-status").forEach(function (pill) {
      var key = pill.getAttribute("data-channel-key");
      var channel = byKey && byKey[key];
      if (!channel) return;
      pill.className =
        "status-pill status-pill--" +
        channel.tone +
        " js-comm-field-status";
      pill.setAttribute("data-channel-key", key);
      pill.textContent = channel.status_label;
      pill.title = channel.detail || "";
    });
  }

  function applyResult(data) {
    if (overallPill) {
      overallPill.className =
        "status-pill status-pill--" +
        (data.overall_tone || "suspended") +
        " js-comm-overall-pill";
      overallPill.textContent = data.overall_label || "Status";
    }
    if (overallDetail) {
      overallDetail.textContent = data.overall_detail || "";
    }
    if (verifiedAt) {
      if (data.verified_at) {
        var when = new Date(data.verified_at);
        verifiedAt.hidden = false;
        verifiedAt.textContent =
          "Last verified " +
          (isNaN(when.getTime())
            ? data.verified_at
            : when.toLocaleString(undefined, {
                dateStyle: "medium",
                timeStyle: "short",
              }));
      } else {
        verifiedAt.hidden = true;
      }
    }
    if (list && Array.isArray(data.connection_channels)) {
      list.innerHTML = data.connection_channels.map(renderChannelItem).join("");
    }
    updateFieldPills(data.by_key || {});
    highlightProblems(data);
  }

  function markChecking() {
    clearFieldProblems();
    if (overallPill) {
      overallPill.className =
        "status-pill status-pill--partial js-comm-overall-pill";
      overallPill.textContent = "Verifying configuration…";
    }
    if (overallDetail) {
      overallDetail.textContent =
        "Running live checks against SMTP and provider APIs.";
    }
    page.querySelectorAll(".js-comm-field-status").forEach(function (pill) {
      var key = pill.getAttribute("data-channel-key");
      var enabledKey = key + "_enabled";
      var enabledInput = fieldInput(enabledKey);
      var enabled = enabledInput ? !!enabledInput.checked : false;
      if (!enabled) {
        pill.className =
          "status-pill status-pill--suspended js-comm-field-status";
        pill.setAttribute("data-channel-key", key);
        pill.textContent = "Disabled";
        return;
      }
      pill.className = "status-pill status-pill--partial js-comm-field-status";
      pill.setAttribute("data-channel-key", key);
      pill.textContent = "Checking…";
    });
  }

  function verify() {
    if (verifying) return Promise.resolve();
    setBusy(true);
    markChecking();
    return fetch(verifyUrl, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        "X-CSRFToken": csrfToken(),
        "X-Requested-With": "XMLHttpRequest",
      },
      body: JSON.stringify({ values: collectValues() }),
    })
      .then(function (resp) {
        return resp.json().then(function (data) {
          if (!resp.ok || !data.ok) {
            throw new Error(
              (data && (data.error || data.detail)) || "Verification failed"
            );
          }
          applyResult(data);
        });
      })
      .catch(function () {
        clearFieldProblems();
        if (overallPill) {
          overallPill.className =
            "status-pill status-pill--pending js-comm-overall-pill";
          overallPill.textContent = "Verification failed";
        }
        if (overallDetail) {
          overallDetail.textContent =
            "Could not complete live checks. Try again.";
        }
      })
      .finally(function () {
        setBusy(false);
      });
  }

  if (btn) {
    btn.addEventListener("click", function () {
      verify();
    });
  }

  // Auto-verify on load so the page always shows live configuration status.
  verify();
})();
