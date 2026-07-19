document.addEventListener("DOMContentLoaded", () => {
  window.initPhoneCountryPicker?.();

  const forceUppercase = (root = document) => {
    root.querySelectorAll("input, textarea").forEach((input) => {
      if (
        input.type === "email" ||
        input.type === "file" ||
        input.type === "hidden" ||
        input.type === "radio" ||
        input.type === "checkbox" ||
        input.type === "search" ||
        input.id === "id_client_email" ||
        input.id === "id_onboard_email"
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
  };
  forceUppercase();

  const typeSelect = document.getElementById("id_client_type");
  const individualNames = document.getElementById("individual-name-fields");
  const corporateNames = document.getElementById("corporate-name-fields");
  const syncType = () => {
    const isCorporate = typeSelect?.value === "corporate";
    individualNames?.classList.toggle("is-hidden", isCorporate);
    corporateNames?.classList.toggle("is-hidden", !isCorporate);
  };
  typeSelect?.addEventListener("change", syncType);
  syncType();

  const providerEl = document.getElementById("email-provider");
  const emailInput = document.getElementById("id_client_email");

  const detectProvider = (email) => {
    const domain = (email || "").split("@")[1]?.toLowerCase() || "";
    if (domain === "gmail.com" || domain === "googlemail.com") return "google";
    if (domain.startsWith("yahoo.")) return "yahoo";
    if (["outlook.com", "hotmail.com", "live.com", "msn.com"].includes(domain)) {
      return "microsoft";
    }
    if (["icloud.com", "me.com", "mac.com"].includes(domain)) return "apple";
    if (["proton.me", "protonmail.com"].includes(domain)) return "proton";
    return "email";
  };

  if (providerEl && emailInput) {
    const sync = () => {
      providerEl.dataset.provider = detectProvider(emailInput.value);
    };
    emailInput.addEventListener("input", sync);
    sync();
  }

  const toggleManual = document.getElementById("toggle-manual-login");
  const manualForm = document.getElementById("manual-login-form");
  if (toggleManual && manualForm) {
    toggleManual.addEventListener("click", () => {
      const open = manualForm.classList.toggle("is-collapsed") === false;
      toggleManual.setAttribute("aria-expanded", String(open));
      if (open) {
        emailInput?.focus();
      }
    });
  }

  const password1 = document.getElementById("id_client_password1");
  const password2 = document.getElementById("id_client_password2");
  const matchStatus = document.getElementById("password-match-status");
  if (password1 && password2 && matchStatus) {
    const syncMatch = () => {
      if (!password2.value) {
        matchStatus.textContent = "";
        return;
      }
      if (password1.value === password2.value) {
        matchStatus.textContent = "Passwords match.";
        matchStatus.style.color = "var(--success)";
      } else {
        matchStatus.textContent = "Passwords do not match.";
        matchStatus.style.color = "var(--danger)";
      }
    };
    password1.addEventListener("input", syncMatch);
    password2.addEventListener("input", syncMatch);
  }

  const photoInput = document.getElementById("id_client_profile_photo");
  const photoPreview = document.getElementById("photo-preview");
  const photoPreviewImg = document.getElementById("photo-preview-img");
  if (photoInput && photoPreview && photoPreviewImg) {
    photoInput.addEventListener("change", () => {
      const file = photoInput.files?.[0];
      if (!file) {
        photoPreview.setAttribute("aria-hidden", "true");
        photoPreviewImg.removeAttribute("src");
        return;
      }
      const url = URL.createObjectURL(file);
      photoPreviewImg.src = url;
      photoPreview.setAttribute("aria-hidden", "false");
    });
  }

  const googleWrap = document.getElementById("google-btn-wrap");
  const googleForm = document.getElementById("google-auth-form");
  const credentialInput = document.getElementById("google-credential");
  const googleStatus = document.getElementById("google-auth-status");

  const setGoogleStatus = (message, isError = false) => {
    if (!googleStatus) return;
    googleStatus.textContent = message || "";
    googleStatus.hidden = !message;
    googleStatus.classList.toggle("field-error", Boolean(isError && message));
  };

  const initGoogle = () => {
    if (!googleWrap) return false;
    if (!window.google?.accounts?.id) return false;

    const clientId = (googleWrap.dataset.clientId || "").trim();
    if (!clientId) {
      setGoogleStatus("Google sign-in is not configured.", true);
      return true;
    }

    try {
      window.google.accounts.id.initialize({
        client_id: clientId,
        callback: (response) => {
          if (!response?.credential || !googleForm || !credentialInput) {
            setGoogleStatus("Google did not return a credential. Try again.", true);
            return;
          }
          setGoogleStatus("Signing you in…");
          credentialInput.value = response.credential;
          googleForm.submit();
        },
        // Popup must be allowed by Cross-Origin-Opener-Policy (same-origin-allow-popups).
        ux_mode: "popup",
        auto_select: false,
        cancel_on_tap_outside: true,
      });

      googleWrap.replaceChildren();
      const width = Math.min(
        Math.max(googleWrap.parentElement?.clientWidth || 320, 240),
        400,
      );
      window.google.accounts.id.renderButton(googleWrap, {
        theme: "outline",
        size: "large",
        text: "continue_with",
        shape: "rectangular",
        width,
        logo_alignment: "left",
      });
      setGoogleStatus("");
      return true;
    } catch (err) {
      console.error("Google Identity Services init failed:", err);
      setGoogleStatus(
        "Could not start Google sign-in. Use email, or check the browser console.",
        true,
      );
      return true;
    }
  };

  if (googleWrap) {
    if (initGoogle()) {
      // ready
    } else {
      setGoogleStatus("Loading Google sign-in…");
      let tries = 0;
      const timer = window.setInterval(() => {
        tries += 1;
        if (initGoogle() || tries > 40) {
          window.clearInterval(timer);
          if (!window.google?.accounts?.id) {
            setGoogleStatus(
              "Google sign-in failed to load. Check your network, or use email.",
              true,
            );
          }
        }
      }, 150);
    }
  }
});
