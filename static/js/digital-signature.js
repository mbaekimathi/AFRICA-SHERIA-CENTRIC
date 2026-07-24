document.addEventListener("DOMContentLoaded", () => {
  const page = document.getElementById("signature-page");
  const form = document.getElementById("signature-form");
  const preview = document.getElementById("signature-preview-stage");
  if (!page || !form || !preview) return;

  const signature = preview.querySelector(".doc-signature");
  const labelEl = document.getElementById("signature-current-label");
  const accentEl = document.getElementById("signature-current-accent");
  const titleEl = signature?.querySelector(".doc-signature__title");
  if (!signature) return;

  const templates = [
    "classic",
    "script",
    "formal",
    "monogram",
    "stacked",
    "compact",
  ];
  const accents = ["forest", "navy", "charcoal", "burgundy", "teal", "gold"];

  const syncCards = () => {
    form.querySelectorAll(".signature-sample-card").forEach((card) => {
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
    const accent = accentInput?.value || "navy";
    const accentHex =
      accentInput?.dataset.signatureAccentHex ||
      signature.style.getPropertyValue("--signature-ink") ||
      "#1e3a5f";

    templates.forEach((key) => {
      signature.classList.toggle(`doc-signature--${key}`, key === template);
    });
    accents.forEach((key) => {
      signature.classList.toggle(
        `doc-signature--accent-${key}`,
        key === accent
      );
    });
    signature.style.setProperty("--signature-ink", accentHex);

    const showFirm = Boolean(
      form.querySelector('input[name="show_firm_name"]')?.checked
    );
    const showName = Boolean(
      form.querySelector('input[name="show_name"]')?.checked
    );
    const showTitle = Boolean(
      form.querySelector('input[name="show_title"]')?.checked
    );
    const showDate = Boolean(
      form.querySelector('input[name="show_date"]')?.checked
    );
    const defaultTitle = (
      form.querySelector('input[name="default_title"]')?.value || ""
    ).trim();

    signature.classList.toggle("doc-signature--no-firm", !showFirm);
    signature.classList.toggle("doc-signature--no-name", !showName);
    signature.classList.toggle("doc-signature--no-title", !showTitle);
    signature.classList.toggle("doc-signature--no-date", !showDate);

    if (titleEl && defaultTitle) {
      titleEl.textContent = defaultTitle;
    }

    if (labelEl && templateInput?.dataset.signatureLabel) {
      labelEl.textContent = templateInput.dataset.signatureLabel;
    }
    if (accentEl && accentInput?.dataset.signatureAccentLabel) {
      accentEl.textContent = accentInput.dataset.signatureAccentLabel;
    }

    syncCards();
  };

  form.addEventListener("change", applyPreview);
  form.addEventListener("input", (event) => {
    if (event.target?.name === "default_title") applyPreview();
  });
  applyPreview();
});
