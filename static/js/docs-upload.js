/**
 * Documents upload — dropzone + edit-details modal.
 */
document.addEventListener("DOMContentLoaded", () => {
  initDropzone();
  initEditModal();
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

function initEditModal() {
  const modal = document.getElementById("docs-edit-modal");
  if (!modal) return;

  const idInput = document.getElementById("docs-edit-id");
  const nameInput = document.getElementById("docs-edit-name");
  const descriptionInput = document.getElementById("docs-edit-description");
  const notesInput = document.getElementById("docs-edit-notes");
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
    return el ? el.textContent : "";
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
