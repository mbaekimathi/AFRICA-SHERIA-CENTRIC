/**
 * Documents upload — dropzone, edit modal, letterhead toggle, submit lock.
 */
document.addEventListener("DOMContentLoaded", () => {
  initDropzone();
  initEditModal();
  initLetterheadToggle();
  initSubmitLocks();
});

function initDropzone() {
  const form = document.querySelector("[data-docs-upload]");
  if (!form) return;

  const drop = form.querySelector("[data-docs-drop]");
  const input = form.querySelector('input[type="file"]');
  const title = form.querySelector("[data-docs-drop-title]");
  const meta = form.querySelector("[data-docs-drop-meta]");
  if (!drop || !input || !title || !meta) return;

  const defaultTitle = title.textContent;
  const defaultMeta = meta.textContent;

  const formatSize = (bytes) => {
    if (!Number.isFinite(bytes) || bytes <= 0) return "";
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const syncFile = () => {
    const file = input.files && input.files[0];
    if (!file) {
      drop.classList.remove("has-file");
      title.textContent = defaultTitle;
      meta.textContent = defaultMeta;
      return;
    }
    drop.classList.add("has-file");
    title.textContent = file.name;
    const size = formatSize(file.size);
    meta.textContent = size ? `${size} · ready to upload` : "Ready to upload";
  };

  input.addEventListener("change", syncFile);

  ["dragenter", "dragover"].forEach((eventName) => {
    drop.addEventListener(eventName, (event) => {
      event.preventDefault();
      event.stopPropagation();
      drop.classList.add("is-dragging");
    });
  });

  ["dragleave", "drop"].forEach((eventName) => {
    drop.addEventListener(eventName, (event) => {
      event.preventDefault();
      event.stopPropagation();
      drop.classList.remove("is-dragging");
    });
  });

  drop.addEventListener("drop", (event) => {
    const files = event.dataTransfer?.files;
    if (!files || !files.length) return;
    const transfer = new DataTransfer();
    transfer.items.add(files[0]);
    input.files = transfer.files;
    syncFile();
  });

  syncFile();
}

function initLetterheadToggle() {
  const section = document.querySelector("[data-docs-letterhead]");
  if (!section) return;

  const form = section.closest("[data-docs-create]") || section.closest("form");
  const toggle =
    section.querySelector("[data-docs-letterhead-toggle]") ||
    section.querySelector('input[type="checkbox"]');
  const preview = section.querySelector("[data-docs-letterhead-preview]");
  const offNote = section.querySelector("[data-docs-letterhead-off]");
  const docsOnly = section.querySelector("[data-docs-letterhead-docs-only]");
  const switchLabel = section.querySelector(".docs-letterhead__switch-label");

  const selectedType = () => {
    if (!form) return "document";
    const checked = form.querySelector(
      'input[name$="google_type"]:checked, input.docs-type-input:checked'
    );
    return checked?.value || "document";
  };

  const sync = () => {
    const enabled = Boolean(toggle?.checked);
    const isDoc = selectedType() === "document";

    if (switchLabel) {
      switchLabel.textContent = enabled ? "Enabled" : "Disabled";
    }
    section.classList.toggle("is-enabled", enabled);
    section.classList.toggle("is-disabled", !enabled);

    if (preview) {
      preview.hidden = !enabled || !isDoc;
    }
    if (offNote) {
      offNote.hidden = enabled;
    }
    if (docsOnly) {
      docsOnly.hidden = !enabled || isDoc;
    }
  };

  toggle?.addEventListener("change", sync);
  form
    ?.querySelectorAll('input[name$="google_type"], input.docs-type-input')
    .forEach((input) => {
      input.addEventListener("change", sync);
    });
  sync();
}

function showDocsBusy(title, message) {
  const overlay = document.getElementById("docs-busy-overlay");
  if (!overlay) return;

  const titleEl = document.getElementById("docs-busy-title");
  const textEl = document.getElementById("docs-busy-text");
  if (titleEl && title) titleEl.textContent = title;
  if (textEl && message) textEl.textContent = message;

  overlay.hidden = false;
  document.body.classList.add("docs-is-busy");
}

function lockSubmitButtons() {
  document
    .querySelectorAll(
      "[data-docs-upload] button[type='submit'], [data-docs-create] button[type='submit'], #docs-edit-form button[type='submit']"
    )
    .forEach((button) => {
      button.disabled = true;
      button.setAttribute("aria-busy", "true");
    });
}

function initSubmitLocks() {
  let isBusy = false;

  const lockAndShow = (kind) => {
    if (isBusy) return false;
    isBusy = true;
    lockSubmitButtons();

    if (kind === "upload") {
      showDocsBusy(
        "Uploading document",
        "Saving your file to Drive. Please wait — do not submit again."
      );
    } else if (kind === "create") {
      showDocsBusy(
        "Creating Google file",
        "Setting up your file in Drive. Please wait — do not submit again."
      );
    } else {
      showDocsBusy(
        "Saving document details",
        "Updating your document. Please wait — do not submit again."
      );
    }
    return true;
  };

  const bindForm = (selector, kind) => {
    const form = document.querySelector(selector);
    if (!form) return;
    form.addEventListener("submit", (event) => {
      if (!lockAndShow(kind)) {
        event.preventDefault();
        event.stopPropagation();
      }
    });
  };

  bindForm("[data-docs-upload]", "upload");
  bindForm("[data-docs-create]", "create");
  bindForm("#docs-edit-form", "edit");
}

function initEditModal() {
  const modal = document.getElementById("docs-edit-modal");
  if (!modal) return;

  const form = document.getElementById("docs-edit-form");
  const idInput = document.getElementById("docs-edit-id");
  const nameInput = document.getElementById("docs-edit-name");
  const descriptionInput = document.getElementById("docs-edit-description");
  const notesInput = document.getElementById("docs-edit-notes");
  const partyTypeInput =
    form?.querySelector('select[name="party_type"]') ||
    document.getElementById("id_party_type") ||
    document.getElementById("edit_party_type");
  const typeLabel = document.getElementById("docs-edit-type");
  const closeBtn = document.getElementById("docs-edit-close");
  const cancelBtn = document.getElementById("docs-edit-cancel");

  const openModal = () => {
    if (typeof modal.showModal === "function") {
      if (!modal.open) modal.showModal();
    } else {
      modal.setAttribute("open", "");
    }
    window.setTimeout(() => nameInput?.focus(), 0);
  };

  const closeModal = () => {
    if (typeof modal.close === "function") {
      modal.close();
    } else {
      modal.removeAttribute("open");
    }
  };

  const fieldText = (source, name) => {
    const el = source.querySelector(`[data-field="${name}"]`);
    return el ? el.textContent.trim() : "";
  };

  const fillFrom = (documentId) => {
    const source = document.querySelector(
      `[data-docs-edit-source="${CSS.escape(String(documentId))}"]`
    );
    if (!source || !idInput || !nameInput || !descriptionInput || !notesInput) {
      return false;
    }
    idInput.value = String(documentId);
    nameInput.value = fieldText(source, "title");
    descriptionInput.value = fieldText(source, "description");
    notesInput.value = fieldText(source, "notes");
    if (partyTypeInput) {
      partyTypeInput.value = fieldText(source, "party_type") || "";
    }
    if (typeLabel) {
      typeLabel.textContent = fieldText(source, "type") || "Document";
    }
    return true;
  };

  document.querySelectorAll("[data-docs-edit]").forEach((button) => {
    button.addEventListener("click", () => {
      const documentId = button.getAttribute("data-id");
      if (!documentId || !fillFrom(documentId)) return;
      openModal();
    });
  });

  closeBtn?.addEventListener("click", closeModal);
  cancelBtn?.addEventListener("click", closeModal);

  modal.addEventListener("click", (event) => {
    if (event.target === modal) closeModal();
  });
}
