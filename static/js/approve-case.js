document.addEventListener("DOMContentLoaded", () => {
  const modal = document.getElementById("case-allocate-modal");
  const openBtn = document.getElementById("open-allocate-modal");
  const closeBtn = document.getElementById("close-allocate-modal");
  const form = document.getElementById("case-allocate-form");
  const assignee = document.getElementById("id_assigned_to");
  const dueDate = document.getElementById("id_due_date");

  if (!modal || !openBtn) return;

  const openModal = () => {
    if (typeof modal.showModal === "function") {
      modal.showModal();
    } else {
      modal.setAttribute("open", "");
    }
    window.setTimeout(() => assignee?.focus(), 0);
  };

  const closeModal = () => {
    if (typeof modal.close === "function") {
      modal.close();
    } else {
      modal.removeAttribute("open");
    }
  };

  openBtn.addEventListener("click", openModal);
  closeBtn?.addEventListener("click", closeModal);

  modal.addEventListener("click", (event) => {
    if (event.target === modal) closeModal();
  });

  if (modal.hasAttribute("open") && typeof modal.showModal === "function") {
    // Re-open properly after validation errors (native dialog attribute alone is inconsistent)
    modal.removeAttribute("open");
    openModal();
  }

  form?.addEventListener("submit", (event) => {
    if (!assignee?.value) {
      event.preventDefault();
      assignee?.reportValidity?.();
      assignee?.focus();
      return;
    }
    if (!dueDate?.value) {
      event.preventDefault();
      dueDate?.reportValidity?.();
      dueDate?.focus();
    }
  });
});
