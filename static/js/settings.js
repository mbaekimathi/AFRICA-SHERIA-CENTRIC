document.addEventListener("DOMContentLoaded", () => {
  const page = document.getElementById("settings-page");
  if (!page) return;

  const body = document.body;
  const roleTheme = page.dataset.roleTheme || "employee";
  const saved = {
    theme: page.dataset.savedTheme || "default",
    font: page.dataset.savedFont || "plex",
    density: page.dataset.savedDensity || "comfortable",
  };

  const editDrop = document.getElementById("edit-profile-drop");
  const editForm = document.getElementById("edit-profile-form");
  const closeEdit = document.getElementById("close-edit-profile");
  const savebar = document.getElementById("appearance-savebar");
  const form = document.getElementById("appearance-form");

  const chipTheme = document.getElementById("chip-theme");
  const chipThemeDisplay = document.getElementById("chip-theme-display");
  const chipThemeMeta = document.getElementById("chip-theme-meta");
  const chipFont = document.getElementById("chip-font");
  const chipDensity = document.getElementById("chip-density");
  const previewTheme = document.getElementById("preview-theme");
  const previewFont = document.getElementById("preview-font");
  const previewDensity = document.getElementById("preview-density");

  closeEdit?.addEventListener("click", () => {
    if (editDrop) editDrop.open = false;
  });

  if (editDrop?.open) {
    window.setTimeout(() => {
      editForm?.querySelector("input, select, textarea")?.focus();
    }, 0);
  }

  const syncIdFields = () => {
    const selected = editForm?.querySelector('input[name="id_type"]:checked');
    const isCitizen = !selected || selected.value === "citizen";
    const citizen = editForm?.querySelector("[data-id-citizen]");
    const nonCitizen = editForm?.querySelector("[data-id-non-citizen]");
    if (citizen) citizen.hidden = !isCitizen;
    if (nonCitizen) nonCitizen.hidden = isCitizen;
  };

  editForm?.querySelectorAll('input[name="id_type"]').forEach((input) => {
    input.addEventListener("change", syncIdFields);
  });
  syncIdFields();

  const syncPaymentFields = () => {
    const selected = editForm?.querySelector('input[name="payment_method"]:checked');
    const method = selected?.value || "";
    const mobile = editForm?.querySelector("[data-payment-mobile]");
    const bank = editForm?.querySelector("[data-payment-bank]");
    if (mobile) mobile.hidden = method !== "mobile";
    if (bank) bank.hidden = method !== "bank";
  };

  editForm?.querySelectorAll('input[name="payment_method"]').forEach((input) => {
    input.addEventListener("change", syncPaymentFields);
  });
  syncPaymentFields();

  const tabs = [...page.querySelectorAll(".settings-tab")];
  const panels = {
    themes: document.getElementById("panel-themes"),
    fonts: document.getElementById("panel-fonts"),
    density: document.getElementById("panel-density"),
  };

  const activateTab = (name) => {
    tabs.forEach((tab) => {
      const active = tab.dataset.tab === name;
      tab.classList.toggle("is-active", active);
      tab.setAttribute("aria-selected", active ? "true" : "false");
    });
    page.querySelectorAll(".theme-admin__panel-actions [data-tab]").forEach((btn) => {
      const active = btn.dataset.tab === name;
      btn.classList.toggle("is-active", active);
      btn.classList.toggle("btn--primary", active);
      btn.classList.toggle("btn--quiet", !active);
    });
    Object.entries(panels).forEach(([key, panel]) => {
      if (!panel) return;
      panel.hidden = key !== name;
    });
  };

  tabs.forEach((tab) => {
    tab.addEventListener("click", () => activateTab(tab.dataset.tab));
  });

  page.querySelectorAll(".theme-admin__panel-actions [data-tab]").forEach((btn) => {
    btn.addEventListener("click", () => activateTab(btn.dataset.tab));
  });

  const replacePrefixClass = (prefix, next) => {
    [...body.classList]
      .filter((name) => name.startsWith(prefix))
      .forEach((name) => body.classList.remove(name));
    body.classList.add(`${prefix}${next}`);
  };

  const currentValues = () => ({
    theme:
      form?.querySelector('input[name="ui_theme"]:checked')?.value ||
      form?.querySelector('input[name="default_ui_theme"]:checked')?.value ||
      saved.theme,
    font: form?.querySelector('input[name="ui_font"]:checked')?.value || saved.font,
    density:
      form?.querySelector('input[name="ui_density"]:checked')?.value || saved.density,
  });

  const syncDirty = () => {
    const now = currentValues();
    const dirty =
      now.theme !== saved.theme ||
      now.font !== saved.font ||
      now.density !== saved.density;
    savebar?.classList.toggle("is-visible", dirty);
  };

  const setLabel = (nodes, text) => {
    nodes.forEach((node) => {
      if (node) node.textContent = text;
    });
  };

  page.querySelectorAll("[data-theme-preview]").forEach((input) => {
    input.addEventListener("change", () => {
      page.querySelectorAll(".theme-card").forEach((el) => el.classList.remove("is-selected"));
      input.closest(".theme-card")?.classList.add("is-selected");
      replacePrefixClass("theme-", input.dataset.themePreview || roleTheme);
      setLabel(
        [chipTheme, chipThemeDisplay, chipThemeMeta, previewTheme],
        input.dataset.themeLabel || "Theme"
      );
      syncDirty();
    });
  });

  page.querySelectorAll("[data-font-preview]").forEach((input) => {
    input.addEventListener("change", () => {
      page.querySelectorAll(".font-card").forEach((el) => el.classList.remove("is-selected"));
      input.closest(".font-card")?.classList.add("is-selected");
      replacePrefixClass("font-", input.dataset.fontPreview || "plex");
      setLabel([chipFont, previewFont], input.dataset.fontLabel || "Typography");
      syncDirty();
    });
  });

  page.querySelectorAll("[data-density-preview]").forEach((input) => {
    input.addEventListener("change", () => {
      page.querySelectorAll(".density-card").forEach((el) => el.classList.remove("is-selected"));
      input.closest(".density-card")?.classList.add("is-selected");
      replacePrefixClass("density-", input.dataset.densityPreview || "comfortable");
      setLabel([chipDensity, previewDensity], input.dataset.densityLabel || "Density");
      syncDirty();
    });
  });

  syncDirty();

  const volumeRoot = document.getElementById("notification-volume-control");
  const volumeSlider = document.getElementById("id_notification_sound_volume");
  const volumeValue = document.getElementById("notification-volume-value");
  const volumeDown = document.getElementById("notification-volume-down");
  const volumeUp = document.getElementById("notification-volume-up");
  const volumeStep = Number(volumeRoot?.dataset.volumeStep || 5);

  function clampVolume(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return 70;
    return Math.max(0, Math.min(100, Math.round(n)));
  }

  function readVolume() {
    return clampVolume(volumeSlider?.value ?? 70);
  }

  function writeVolume(value) {
    const next = clampVolume(value);
    if (volumeSlider) volumeSlider.value = String(next);
    if (volumeValue) volumeValue.textContent = `${next}%`;
    const menu = document.getElementById("notif-menu");
    if (menu) menu.dataset.soundVolume = String(next);
    return next;
  }

  volumeSlider?.addEventListener("input", () => {
    writeVolume(volumeSlider.value);
  });

  volumeDown?.addEventListener("click", () => {
    writeVolume(readVolume() - volumeStep);
  });

  volumeUp?.addEventListener("click", () => {
    writeVolume(readVolume() + volumeStep);
  });

  if (volumeSlider) writeVolume(volumeSlider.value);

  const browserToggle = document.getElementById("id_notification_browser");
  const browserStatus = document.getElementById("notification-browser-status");
  const enableBrowserBtn = document.getElementById("enable-browser-notifications");
  const testBrowserBtn = document.getElementById("test-browser-notification");

  function browserSupported() {
    return typeof window.Notification === "function";
  }

  function browserPermission() {
    if (!browserSupported()) return "unsupported";
    return window.Notification.permission || "default";
  }

  async function requestBrowserPermission() {
    if (!browserSupported()) return "unsupported";
    if (browserPermission() !== "default") return browserPermission();
    try {
      const result = await window.Notification.requestPermission();
      return result || browserPermission();
    } catch (_error) {
      return browserPermission();
    }
  }

  function showBrowserTestNotification() {
    if (!browserSupported() || browserPermission() !== "granted") return false;
    const firm =
      document.getElementById("notif-menu")?.dataset.firmName || "Sheria Centric";
    try {
      const note = new window.Notification(`${firm} · Test browser alert`, {
        body: "Browser notifications are working for Sheria Centric.",
        tag: `sheria-test-${Date.now()}`,
      });
      note.onclick = () => {
        try {
          window.focus();
        } catch (_error) {
          // Ignore.
        }
        note.close();
      };
      window.setTimeout(() => {
        try {
          note.close();
        } catch (_error) {
          // Ignore.
        }
      }, 8000);
      return true;
    } catch (_error) {
      return false;
    }
  }

  function setEnableBrowserVisible(visible) {
    if (!enableBrowserBtn) return;
    enableBrowserBtn.hidden = !visible;
    enableBrowserBtn.style.display = visible ? "" : "none";
    if (visible) enableBrowserBtn.removeAttribute("hidden");
    else enableBrowserBtn.setAttribute("hidden", "");
  }

  function syncBrowserPermissionUi() {
    if (!browserStatus) return;

    browserStatus.classList.remove("is-granted", "is-denied");
    if (!browserSupported()) {
      browserStatus.textContent =
        "This browser does not support desktop notifications.";
      setEnableBrowserVisible(false);
      return;
    }

    const perm = browserPermission();
    if (perm === "granted") {
      browserStatus.textContent = "Browser alerts are allowed on this device.";
      browserStatus.classList.add("is-granted");
      setEnableBrowserVisible(false);
      return;
    }
    if (perm === "denied") {
      browserStatus.textContent =
        "Browser alerts are blocked. Allow notifications for this site in your browser settings, then reload.";
      browserStatus.classList.add("is-denied");
      setEnableBrowserVisible(false);
      return;
    }

    browserStatus.textContent =
      "Browser permission is not granted yet. Click Allow browser alerts to enable them.";
    setEnableBrowserVisible(true);
  }

  enableBrowserBtn?.addEventListener("click", async () => {
    const perm = await requestBrowserPermission();
    syncBrowserPermissionUi();
    if (perm === "granted") {
      if (browserToggle && !browserToggle.checked) browserToggle.checked = true;
      const menu = document.getElementById("notif-menu");
      if (menu) menu.dataset.browserEnabled = "true";
      showBrowserTestNotification();
    }
  });

  browserToggle?.addEventListener("change", async () => {
    const menu = document.getElementById("notif-menu");
    if (menu) {
      menu.dataset.browserEnabled = browserToggle.checked ? "true" : "false";
    }
    if (browserToggle.checked && browserPermission() === "default") {
      await requestBrowserPermission();
    }
    syncBrowserPermissionUi();
  });

  testBrowserBtn?.addEventListener("click", async () => {
    if (browserPermission() === "default") {
      await requestBrowserPermission();
    }
    syncBrowserPermissionUi();
    if (browserPermission() !== "granted") return;
    if (!showBrowserTestNotification() && window.SheriaBrowserNotifications) {
      window.SheriaBrowserNotifications.show(
        {
          id: `test-${Date.now()}`,
          title: "Test browser alert",
          body: "Browser notifications are working for Sheria Centric.",
          url: window.location.href,
        },
        { force: true }
      );
    }
  });

  syncBrowserPermissionUi();
  window.addEventListener("sheria:notifications-ready", syncBrowserPermissionUi);

  function playFallbackChime(volumePct) {
    try {
      const AudioContext = window.AudioContext || window.webkitAudioContext;
      if (!AudioContext) return false;
      if (volumePct <= 0) return false;
      const volumeScale = volumePct / 100;
      const ctx = new AudioContext();
      const playTone = (frequency, startAt, duration, gainValue) => {
        const oscillator = ctx.createOscillator();
        const gain = ctx.createGain();
        oscillator.type = "sine";
        oscillator.frequency.value = frequency;
        gain.gain.setValueAtTime(0.0001, startAt);
        gain.gain.exponentialRampToValueAtTime(
          Math.max(0.0001, gainValue),
          startAt + 0.02
        );
        gain.gain.exponentialRampToValueAtTime(0.0001, startAt + duration);
        oscillator.connect(gain);
        gain.connect(ctx.destination);
        oscillator.start(startAt);
        oscillator.stop(startAt + duration + 0.02);
      };
      const start = () => {
        const t = ctx.currentTime;
        playTone(880, t, 0.14, 0.12 * volumeScale);
        playTone(1174.7, t + 0.12, 0.18, 0.09 * volumeScale);
      };
      if (ctx.state === "suspended") {
        ctx.resume().then(start).catch(() => {});
      } else {
        start();
      }
      return true;
    } catch (_error) {
      return false;
    }
  }

  const testSoundBtn = document.getElementById("test-notification-sound");
  testSoundBtn?.addEventListener("click", () => {
    const volumePct = readVolume();
    const sound = window.SheriaNotificationSound;
    if (sound) {
      sound.unlock();
      sound.play(true);
      return;
    }
    playFallbackChime(volumePct);
  });
});
