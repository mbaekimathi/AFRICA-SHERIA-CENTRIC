document.addEventListener("DOMContentLoaded", () => {
  const page = document.getElementById("letterhead-page");
  const form = document.getElementById("letterhead-form");
  const preview = document.getElementById("letterhead-preview-stage");
  if (!page || !form || !preview) return;

  const header = preview.querySelector(".doc-letterhead");
  const labelEl = document.getElementById("letterhead-current-label");
  const accentEl = document.getElementById("letterhead-current-accent");
  if (!header) return;

  const templates = [
    "classic",
    "centered",
    "banner",
    "ruled",
    "split",
    "minimal",
  ];
  const accents = ["forest", "navy", "charcoal", "burgundy", "teal", "gold"];

  const syncCards = () => {
    form.querySelectorAll(".letterhead-sample-card").forEach((card) => {
      const input = card.querySelector('input[type="radio"]');
      card.classList.toggle("is-selected", Boolean(input?.checked));
    });
    form.querySelectorAll(".letterhead-accent-chip").forEach((chip) => {
      const input = chip.querySelector('input[type="radio"]');
      chip.classList.toggle("is-selected", Boolean(input?.checked));
    });
  };

  const applyPreview = () => {
    const templateInput = form.querySelector(
      'input[name="template"]:checked'
    );
    const accentInput = form.querySelector('input[name="accent"]:checked');
    const template = templateInput?.value || "classic";
    const accent = accentInput?.value || "forest";
    const accentHex =
      accentInput?.dataset.letterheadAccentHex ||
      header.style.getPropertyValue("--lh-accent") ||
      "#0f6e56";

    templates.forEach((key) => {
      header.classList.toggle(`doc-letterhead--${key}`, key === template);
    });
    accents.forEach((key) => {
      header.classList.toggle(`doc-letterhead--accent-${key}`, key === accent);
    });
    header.style.setProperty("--lh-accent", accentHex);

    const showLogo = Boolean(
      form.querySelector('input[name="show_logo"]')?.checked
    );
    const showTagline = Boolean(
      form.querySelector('input[name="show_tagline"]')?.checked
    );
    const showAddress = Boolean(
      form.querySelector('input[name="show_address"]')?.checked
    );
    const showContacts = Boolean(
      form.querySelector('input[name="show_contacts"]')?.checked
    );

    header.classList.toggle("doc-letterhead--no-logo", !showLogo);
    header.classList.toggle("doc-letterhead--no-tagline", !showTagline);
    header.classList.toggle("doc-letterhead--no-address", !showAddress);
    header.classList.toggle("doc-letterhead--no-contacts", !showContacts);

    if (labelEl && templateInput?.dataset.letterheadLabel) {
      labelEl.textContent = templateInput.dataset.letterheadLabel;
    }
    if (accentEl && accentInput?.dataset.letterheadAccentLabel) {
      accentEl.textContent = accentInput.dataset.letterheadAccentLabel;
    }

    syncCards();
  };

  form.addEventListener("change", applyPreview);
  applyPreview();
});
