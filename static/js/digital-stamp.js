document.addEventListener("DOMContentLoaded", () => {
  const page = document.getElementById("stamp-page");
  const form = document.getElementById("stamp-form");
  if (!page || !form) return;

  const preview = document.getElementById("stamp-preview-stage");
  const stamp = preview?.querySelector(".doc-stamp");
  const labelEl = document.getElementById("stamp-current-label");
  const accentEl = document.getElementById("stamp-current-accent");

  const templates = [
    "classic",
    "advocate",
    "square",
    "oval",
    "badge",
    "ribbon",
    "wax",
  ];
  const accents = [
    "ink",
    "forest",
    "navy",
    "charcoal",
    "burgundy",
    "teal",
    "gold",
  ];

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
    if (!stamp || stamp.classList.contains("doc-stamp--scan")) {
      syncCards();
      return;
    }

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

  form.addEventListener("change", (event) => {
    if (event.target?.matches?.("[data-stamp-upload]")) return;
    applyPreview();
  });
  applyPreview();

  // Uploaded stamp: show the chosen file before it is saved.
  const upload = form.querySelector("[data-stamp-upload]");
  const uploadSection = document.getElementById("stamp-upload");
  const uploadPreview = form.querySelector("[data-stamp-upload-preview]");
  const uploadName = form.querySelector("[data-stamp-upload-name]");
  const uploadPlaceholder = form.querySelector(
    "[data-stamp-upload-placeholder]"
  );
  const uploadKicker = form.querySelector("[data-stamp-upload-kicker]");
  const submitBtn = form.querySelector('button[type="submit"]');
  let previewObjectUrl = "";

  const showChosenStamp = (file) => {
    if (!file || !uploadPreview) return;

    if (previewObjectUrl) {
      URL.revokeObjectURL(previewObjectUrl);
    }
    previewObjectUrl = URL.createObjectURL(file);
    uploadPreview.src = previewObjectUrl;
    uploadPreview.alt = file.name || "Uploaded stamp";
    uploadPreview.hidden = false;
    uploadPreview.removeAttribute("hidden");

    if (uploadPlaceholder) {
      uploadPlaceholder.hidden = true;
      uploadPlaceholder.setAttribute("hidden", "");
    }
    if (uploadName) uploadName.textContent = file.name;
    if (uploadKicker) uploadKicker.textContent = "Ready to save";
    uploadSection?.classList.add("stamp-upload--active");

    // Mirror into the live preview so the user sees what documents will use.
    const canvas = preview?.querySelector(".stamp-preview__canvas");
    if (canvas) {
      canvas.innerHTML = `
        <div class="doc-stamp doc-stamp--scan" role="img" aria-label="Uploaded stamp preview">
          <img class="doc-stamp__scan" src="${previewObjectUrl}" alt="">
        </div>
      `;
    }

    if (submitBtn && !submitBtn.dataset.defaultLabel) {
      submitBtn.dataset.defaultLabel = submitBtn.textContent.trim();
    }
    if (submitBtn) {
      submitBtn.textContent = submitBtn.dataset.saveUploadLabel || "Save uploaded stamp";
    }
  };

  if (upload && uploadPreview) {
    upload.addEventListener("change", () => {
      const file = upload.files && upload.files[0];
      if (!file) return;
      if (!file.type.startsWith("image/")) return;
      showChosenStamp(file);
    });
  }
});
