(function () {
  var page = document.getElementById("company-contacts-page");
  if (!page) return;

  var verifyUrl = page.getAttribute("data-contact-verify-url");
  if (!verifyUrl) return;

  var form = document.getElementById("company-contacts-form");
  var list = page.querySelector(".js-contact-connections-list");
  var overallPill = page.querySelector(".js-contact-overall-pill");
  var overallDetail = page.querySelector(".js-contact-overall-detail");
  var verifiedAt = page.querySelector(".js-contact-verified-at");
  var btn = page.querySelector(".js-contact-verify-btn");
  var spinner = page.querySelector(".js-contact-verify-spinner");
  var btnLabel = page.querySelector(".js-contact-verify-label");
  var verifying = false;

  var FIELD_KEYS = [
    "email",
    "phone",
    "website",
    "linkedin_url",
    "facebook_url",
    "instagram_url",
    "x_url",
    "youtube_url",
    "physical_address",
    "postal_address",
    "city",
    "country",
  ];

  function csrfToken() {
    var input = form
      ? form.querySelector("[name=csrfmiddlewaretoken]")
      : document.querySelector("[name=csrfmiddlewaretoken]");
    if (input && input.value) return input.value;
    var match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  function fieldInput(key) {
    if (!form) return null;
    var map = {
      email: "id_company_email",
      phone: "id_company_phone",
      website: "id_company_website",
      linkedin_url: "id_company_linkedin_url",
      facebook_url: "id_company_facebook_url",
      instagram_url: "id_company_instagram_url",
      x_url: "id_company_x_url",
      youtube_url: "id_company_youtube_url",
      physical_address: "id_company_physical_address",
      postal_address: "id_company_postal_address",
      city: "id_company_city",
      country: "id_company_country",
    };
    var id = map[key];
    return id ? document.getElementById(id) : null;
  }

  function collectValues() {
    var values = {};
    FIELD_KEYS.forEach(function (key) {
      var input = fieldInput(key);
      values[key] = input ? String(input.value || "").trim() : "";
    });
    return values;
  }

  function setBusy(busy) {
    verifying = busy;
    if (btn) btn.disabled = busy;
    if (spinner) spinner.hidden = !busy;
    if (btnLabel) {
      btnLabel.textContent = busy ? "Verifying…" : "Verify connections";
    }
  }

  function escapeHtml(text) {
    return String(text || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
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
    return (
      '<li class="contact-connections__item" data-channel-key="' +
      escapeHtml(channel.key) +
      '" data-status="' +
      escapeHtml(channel.status) +
      '">' +
      '<div class="contact-connections__item-main">' +
      '<span class="contact-connections__label">' +
      escapeHtml(channel.label) +
      "</span>" +
      valueHtml +
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
    page.querySelectorAll(".js-field-status").forEach(function (pill) {
      var key = pill.getAttribute("data-field-key");
      var channel = byKey && byKey[key];
      if (!channel) return;
      pill.className =
        "field-status status-pill status-pill--" +
        channel.tone +
        " js-field-status";
      pill.setAttribute("data-field-key", key);
      pill.textContent = channel.status_label;
      pill.title = channel.detail || "";
    });
  }

  function applyResult(data) {
    if (overallPill) {
      overallPill.className =
        "status-pill status-pill--" +
        (data.overall_tone || "suspended") +
        " js-contact-overall-pill";
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
      list.innerHTML = data.connection_channels
        .map(renderChannelItem)
        .join("");
    }
    updateFieldPills(data.by_key || {});
  }

  function markChecking() {
    if (overallPill) {
      overallPill.className =
        "status-pill status-pill--partial js-contact-overall-pill";
      overallPill.textContent = "Verifying connections…";
    }
    if (overallDetail) {
      overallDetail.textContent =
        "Checking email, phone, website, and social profiles.";
    }
    page.querySelectorAll(".js-field-status").forEach(function (pill) {
      var key = pill.getAttribute("data-field-key");
      var input = fieldInput(key);
      var hasValue = input && String(input.value || "").trim();
      if (!hasValue) {
        pill.className =
          "field-status status-pill status-pill--suspended js-field-status";
        pill.setAttribute("data-field-key", key);
        pill.textContent = "Not set";
        return;
      }
      pill.className =
        "field-status status-pill status-pill--partial js-field-status";
      pill.setAttribute("data-field-key", key);
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
        if (overallPill) {
          overallPill.className =
            "status-pill status-pill--pending js-contact-overall-pill";
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

  // Auto-verify on load so the page always shows live connection status.
  verify();
})();
