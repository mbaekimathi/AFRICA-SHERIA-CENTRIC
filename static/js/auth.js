document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".link-btn[data-target], #toggle-password").forEach((btn) => {
    btn.addEventListener("click", () => {
      const targetId = btn.dataset.target || "id_password";
      const input = document.getElementById(targetId);
      if (!input) return;
      const showing = input.type === "text";
      input.type = showing ? "password" : "text";
      btn.textContent = showing ? "Show" : "Hide";
      btn.setAttribute("aria-pressed", String(!showing));
    });
  });

  const toasts = document.querySelectorAll(".toast");
  toasts.forEach((toast) => {
    window.setTimeout(() => {
      toast.style.opacity = "0";
      toast.style.transform = "translateY(-8px)";
      toast.style.transition = "opacity 0.3s ease, transform 0.3s ease";
      window.setTimeout(() => toast.remove(), 320);
    }, 4200);
  });

  const suspendedModal = document.getElementById("suspended-modal");
  const closeSuspended = document.getElementById("close-suspended-modal");
  if (suspendedModal && closeSuspended) {
    closeSuspended.addEventListener("click", () => suspendedModal.close());
  }

  const signupForm = document.getElementById("signup-form");
  if (!signupForm) return;

  const loginCodeInput = document.getElementById("id_login_code");
  const codeStatus = document.getElementById("login-code-status");
  const password1 = document.getElementById("id_password1");
  const password2 = document.getElementById("id_password2");
  const matchStatus = document.getElementById("password-match-status");
  const photoInput = document.getElementById("id_profile_photo");
  const photoPreview = document.getElementById("photo-preview");
  const photoPreviewImg = document.getElementById("photo-preview-img");
  const citizenField = document.getElementById("citizen-id-field");
  const alienField = document.getElementById("alien-id-field");
  const checkUrl = signupForm.dataset.checkCodeUrl;
  const emailInput = signupForm.querySelector('input[type="email"], #id_personal_email');

  signupForm.querySelectorAll("input").forEach((input) => {
    if (
      input.type === "email" ||
      input.type === "file" ||
      input.type === "radio" ||
      input.type === "checkbox" ||
      input.type === "hidden" ||
      input.type === "search" ||
      input === emailInput
    ) {
      return;
    }
    input.classList.add("input-uppercase");
    const forceUpper = () => {
      const start = input.selectionStart;
      const end = input.selectionEnd;
      const upper = input.value.toUpperCase();
      if (input.value !== upper) {
        input.value = upper;
        if (typeof start === "number" && typeof end === "number") {
          input.setSelectionRange(start, end);
        }
      }
    };
    input.addEventListener("input", forceUpper);
    forceUpper();
  });

  const initCountryPickers = () => {
    const dataEl = document.getElementById("country-codes-data");
    if (!dataEl) return;

    const countries = JSON.parse(dataEl.textContent);
    const byIso = Object.fromEntries(countries.map((c) => [c.iso.toUpperCase(), c]));
    const defaultCountry =
      countries.find((c) => c.iso === "ke") || countries[0];

    const phoneHidden = document.getElementById("id_country_code");
    const idHidden = document.getElementById("id_id_country");

    const phoneUi = {
      root: document.getElementById("phone-field"),
      hidden: phoneHidden,
      trigger: document.getElementById("country-trigger"),
      menu: document.getElementById("country-menu"),
      list: document.getElementById("country-list"),
      search: document.getElementById("country-search"),
      flag: document.getElementById("country-flag"),
      dial: document.getElementById("country-dial"),
      mode: "phone",
    };

    const idUi = {
      root: document.getElementById("id-country-field"),
      hidden: idHidden,
      trigger: document.getElementById("id-country-trigger"),
      menu: document.getElementById("id-country-menu"),
      list: document.getElementById("id-country-list"),
      search: document.getElementById("id-country-search"),
      flag: document.getElementById("id-country-flag"),
      name: document.getElementById("id-country-name"),
      mode: "id",
    };

    const resolveFromPhoneValue = (value) =>
      countries.find((c) => c.value === value) || defaultCountry;

    const resolveFromIso = (iso) =>
      byIso[(iso || "KE").toUpperCase()] || defaultCountry;

    const paintPhone = (country) => {
      if (!phoneUi.hidden || !phoneUi.flag || !phoneUi.dial) return;
      phoneUi.hidden.value = country.value;
      phoneUi.flag.src = country.flag;
      phoneUi.flag.srcset = `${country.flag2x} 2x`;
      phoneUi.flag.alt = `${country.name} flag`;
      phoneUi.dial.textContent = country.dial;
      phoneUi.list?.querySelectorAll(".country-option").forEach((btn) => {
        btn.classList.toggle("is-active", btn.dataset.value === country.value);
      });
    };

    const paintId = (country) => {
      if (!idUi.hidden || !idUi.flag || !idUi.name) return;
      idUi.hidden.value = country.iso.toUpperCase();
      idUi.flag.src = country.flag;
      idUi.flag.srcset = `${country.flag2x} 2x`;
      idUi.flag.alt = `${country.name} flag`;
      idUi.name.textContent = country.name;
      idUi.list?.querySelectorAll(".country-option").forEach((btn) => {
        btn.classList.toggle(
          "is-active",
          btn.dataset.iso === country.iso.toUpperCase()
        );
      });
    };

    const setCountry = (country, source) => {
      if (source === "id") {
        paintId(country);
      } else {
        paintPhone(country);
      }
    };

    const renderOptions = (ui, query = "") => {
      const q = query.trim().toLowerCase();
      const filtered = countries.filter(
        (c) =>
          !q ||
          c.name.toLowerCase().includes(q) ||
          c.dial.includes(q) ||
          c.iso.includes(q)
      );
      ui.list.innerHTML = "";
      filtered.forEach((country) => {
        const li = document.createElement("li");
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "country-option";
        btn.dataset.value = country.value;
        btn.dataset.iso = country.iso.toUpperCase();
        btn.setAttribute("role", "option");
        btn.innerHTML = `
          <img class="country-flag" src="${country.flag}" srcset="${country.flag2x} 2x" width="28" height="20" alt="">
          <span class="country-option__name">${country.name}</span>
          <span class="country-option__dial">${
            ui.mode === "phone" ? country.dial : country.iso.toUpperCase()
          }</span>
        `;
        const active =
          ui.mode === "phone"
            ? ui.hidden.value === country.value
            : ui.hidden.value === country.iso.toUpperCase();
        if (active) btn.classList.add("is-active");
        btn.addEventListener("click", () => {
          setCountry(country, ui.mode);
          ui.menu.hidden = true;
          ui.trigger.setAttribute("aria-expanded", "false");
        });
        li.appendChild(btn);
        ui.list.appendChild(li);
      });
    };

    const wirePicker = (ui) => {
      if (!ui.trigger || !ui.menu || !ui.list) return;

      const closeMenu = () => {
        ui.menu.hidden = true;
        ui.trigger.setAttribute("aria-expanded", "false");
      };

      ui.trigger.addEventListener("click", () => {
        const open = ui.menu.hidden;
        document.querySelectorAll(".country-menu").forEach((m) => {
          m.hidden = true;
        });
        document.querySelectorAll(".country-trigger").forEach((t) => {
          t.setAttribute("aria-expanded", "false");
        });
        ui.menu.hidden = !open;
        ui.trigger.setAttribute("aria-expanded", String(open));
        if (open) {
          renderOptions(ui, ui.search?.value || "");
          ui.search?.focus();
        }
      });

      ui.search?.addEventListener("input", () => renderOptions(ui, ui.search.value));

      document.addEventListener("click", (event) => {
        if (ui.root && !ui.root.contains(event.target)) closeMenu();
      });
    };

    wirePicker(phoneUi);
    wirePicker(idUi);

    paintPhone(resolveFromPhoneValue(phoneHidden?.value));
    paintId(resolveFromIso(idHidden?.value));
    renderOptions(phoneUi);
    renderOptions(idUi);
  };

  initCountryPickers();

  let codeTimer = null;
  let codeAvailable = false;

  const setHint = (el, message, state) => {
    if (!el) return;
    el.textContent = message;
    el.classList.remove("is-ok", "is-bad");
    if (state) el.classList.add(state);
  };

  const syncIdType = () => {
    const selected = signupForm.querySelector('input[name="id_type"]:checked');
    const isCitizen = !selected || selected.value === "citizen";
    citizenField?.classList.toggle("is-hidden", !isCitizen);
    alienField?.classList.toggle("is-hidden", isCitizen);
  };

  signupForm.querySelectorAll('input[name="id_type"]').forEach((radio) => {
    radio.addEventListener("change", syncIdType);
  });
  syncIdType();

  const checkLoginCode = async () => {
    const code = (loginCodeInput?.value || "").trim();
    if (!/^\d{6}$/.test(code)) {
      codeAvailable = false;
      setHint(codeStatus, "Enter exactly 6 digits.", code.length ? "is-bad" : "");
      return;
    }
    setHint(codeStatus, "Checking availability…");
    try {
      const response = await fetch(`${checkUrl}?code=${encodeURIComponent(code)}`);
      if (!response.ok) {
        codeAvailable = false;
        setHint(
          codeStatus,
          "Could not verify code right now. Restart the server.",
          "is-bad"
        );
        return;
      }
      const data = await response.json();
      codeAvailable = Boolean(data.available);
      setHint(codeStatus, data.message, data.available ? "is-ok" : "is-bad");
    } catch (_error) {
      codeAvailable = false;
      setHint(
        codeStatus,
        "Could not verify code right now. Restart the server.",
        "is-bad"
      );
    }
  };

  loginCodeInput?.addEventListener("input", () => {
    loginCodeInput.value = loginCodeInput.value.replace(/\D/g, "").slice(0, 6);
    window.clearTimeout(codeTimer);
    codeTimer = window.setTimeout(checkLoginCode, 350);
  });

  if ((loginCodeInput?.value || "").length === 6) {
    checkLoginCode();
  }

  const checkPasswordMatch = () => {
    const p1 = password1?.value || "";
    const p2 = password2?.value || "";
    if (!p2) {
      setHint(matchStatus, "");
      return false;
    }
    if (p1 === p2) {
      setHint(matchStatus, "Passwords match.", "is-ok");
      return true;
    }
    setHint(matchStatus, "Passwords do not match.", "is-bad");
    return false;
  };

  password1?.addEventListener("input", checkPasswordMatch);
  password2?.addEventListener("input", checkPasswordMatch);

  photoInput?.addEventListener("change", () => {
    const file = photoInput.files?.[0];
    if (!file || !photoPreview || !photoPreviewImg) return;
    const url = URL.createObjectURL(file);
    photoPreviewImg.src = url;
    photoPreview.classList.add("is-visible");
  });

  signupForm.addEventListener("submit", (event) => {
    const code = (loginCodeInput?.value || "").trim();
    if (!/^\d{6}$/.test(code) || codeAvailable === false) {
      event.preventDefault();
      setHint(codeStatus, "Choose an available 6-digit login code.", "is-bad");
      loginCodeInput?.focus();
      return;
    }
    if (!checkPasswordMatch()) {
      event.preventDefault();
      password2?.focus();
    }
  });
});
