document.addEventListener("DOMContentLoaded", () => {
  const page = document.getElementById("stamp-page");
  const form = document.getElementById("stamp-form");
  const preview = document.getElementById("stamp-preview-stage");
  if (!page || !form || !preview) return;

  const stamp = preview.querySelector(".doc-stamp");
  const labelEl = document.getElementById("stamp-current-label");
  const accentEl = document.getElementById("stamp-current-accent");
  if (!stamp) return;

  const templates = ["classic", "square", "oval", "badge", "ribbon", "wax"];
  const accents = ["forest", "navy", "charcoal", "burgundy", "teal", "gold"];

  const syncCards = () => {
    form.querySelectorAll(".stamp-sample-card").forEach((card) => {
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
      accentInput?.dataset.stampAccentHex ||
      stamp.style.getPropertyValue("--stamp-ink") ||
      "#0f6e56";

    templates.forEach((key) => {
      stamp.classList.toggle(`doc-stamp--${key}`, key === template);
    });
    accents.forEach((key) => {
      stamp.classList.toggle(`doc-stamp--accent-${key}`, key === accent);
    });
    stamp.style.setProperty("--stamp-ink", accentHex);

    const showFirm = Boolean(
      form.querySelector('input[name="show_firm_name"]')?.checked
    );
    const showStatus = Boolean(
      form.querySelector('input[name="show_status"]')?.checked
    );
    const showApprover = Boolean(
      form.querySelector('input[name="show_approver"]')?.checked
    );
    const showDate = Boolean(
      form.querySelector('input[name="show_date"]')?.checked
    );

    stamp.classList.toggle("doc-stamp--no-firm", !showFirm);
    stamp.classList.toggle("doc-stamp--no-status", !showStatus);
    stamp.classList.toggle("doc-stamp--no-approver", !showApprover);
    stamp.classList.toggle("doc-stamp--no-date", !showDate);

    if (labelEl && templateInput?.dataset.stampLabel) {
      labelEl.textContent = templateInput.dataset.stampLabel;
    }
    if (accentEl && accentInput?.dataset.stampAccentLabel) {
      accentEl.textContent = accentInput.dataset.stampAccentLabel;
    }

    syncCards();
  };

  form.addEventListener("change", applyPreview);
  applyPreview();
});
