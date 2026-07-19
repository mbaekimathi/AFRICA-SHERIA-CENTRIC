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

  const viewModal = document.getElementById("view-profile-modal");
  const editModal = document.getElementById("edit-profile-modal");
  const openView = document.getElementById("open-view-profile");
  const openEdit = document.getElementById("open-edit-profile");
  const closeView = document.getElementById("close-view-profile");
  const closeEdit = document.getElementById("close-edit-profile");
  const viewToEdit = document.getElementById("view-to-edit-profile");
  const savebar = document.getElementById("appearance-savebar");
  const form = document.getElementById("appearance-form");

  const chipTheme = document.getElementById("chip-theme");
  const chipFont = document.getElementById("chip-font");
  const chipDensity = document.getElementById("chip-density");
  const previewTheme = document.getElementById("preview-theme");
  const previewFont = document.getElementById("preview-font");
  const previewDensity = document.getElementById("preview-density");

  const openModal = (modal) => {
    if (!modal) return;
    if (typeof modal.showModal === "function") {
      if (!modal.open) modal.showModal();
    } else {
      modal.setAttribute("open", "");
    }
  };

  const closeModal = (modal) => {
    if (!modal) return;
    if (typeof modal.close === "function") {
      modal.close();
    } else {
      modal.removeAttribute("open");
    }
  };

  openView?.addEventListener("click", () => openModal(viewModal));
  openEdit?.addEventListener("click", () => openModal(editModal));
  closeView?.addEventListener("click", () => closeModal(viewModal));
  closeEdit?.addEventListener("click", () => closeModal(editModal));
  viewToEdit?.addEventListener("click", () => {
    closeModal(viewModal);
    openModal(editModal);
  });

  [viewModal, editModal].forEach((modal) => {
    modal?.addEventListener("click", (event) => {
      if (event.target === modal) closeModal(modal);
    });
  });

  if (viewModal?.hasAttribute("open") && typeof viewModal.showModal === "function") {
    viewModal.removeAttribute("open");
    openModal(viewModal);
  }
  if (editModal?.hasAttribute("open") && typeof editModal.showModal === "function") {
    editModal.removeAttribute("open");
    openModal(editModal);
    window.setTimeout(() => {
      editModal.querySelector("input, select, textarea")?.focus();
    }, 0);
  }

  const syncIdFields = () => {
    const selected = editModal?.querySelector('input[name="id_type"]:checked');
    const isCitizen = !selected || selected.value === "citizen";
    const citizen = editModal?.querySelector("[data-id-citizen]");
    const nonCitizen = editModal?.querySelector("[data-id-non-citizen]");
    if (citizen) citizen.hidden = !isCitizen;
    if (nonCitizen) nonCitizen.hidden = isCitizen;
  };

  editModal?.querySelectorAll('input[name="id_type"]').forEach((input) => {
    input.addEventListener("change", syncIdFields);
  });
  syncIdFields();

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
    Object.entries(panels).forEach(([key, panel]) => {
      if (!panel) return;
      panel.hidden = key !== name;
    });
  };

  tabs.forEach((tab) => {
    tab.addEventListener("click", () => activateTab(tab.dataset.tab));
  });

  const replacePrefixClass = (prefix, next) => {
    [...body.classList]
      .filter((name) => name.startsWith(prefix))
      .forEach((name) => body.classList.remove(name));
    body.classList.add(`${prefix}${next}`);
  };

  const currentValues = () => ({
    theme: form?.querySelector('input[name="ui_theme"]:checked')?.value || saved.theme,
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
      setLabel([chipTheme, previewTheme], input.dataset.themeLabel || "Theme");
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

  const testSoundBtn = document.getElementById("test-notification-sound");
  testSoundBtn?.addEventListener("click", () => {
    const sound = window.SheriaNotificationSound;
    if (sound) {
      sound.unlock();
      sound.play(true);
      return;
    }
    // Fallback if notifications script did not load (should not happen on settings)
    try {
      const AudioContext = window.AudioContext || window.webkitAudioContext;
      if (!AudioContext) return;
      const ctx = new AudioContext();
      const playTone = (frequency, startAt, duration, gainValue) => {
        const oscillator = ctx.createOscillator();
        const gain = ctx.createGain();
        oscillator.type = "sine";
        oscillator.frequency.value = frequency;
        gain.gain.setValueAtTime(0.0001, startAt);
        gain.gain.exponentialRampToValueAtTime(gainValue, startAt + 0.02);
        gain.gain.exponentialRampToValueAtTime(0.0001, startAt + duration);
        oscillator.connect(gain);
        gain.connect(ctx.destination);
        oscillator.start(startAt);
        oscillator.stop(startAt + duration + 0.02);
      };
      const t = ctx.currentTime;
      playTone(880, t, 0.14, 0.045);
      playTone(1174.7, t + 0.12, 0.18, 0.035);
    } catch (_error) {
      // Ignore audio failures in restricted environments.
    }
  });
});
