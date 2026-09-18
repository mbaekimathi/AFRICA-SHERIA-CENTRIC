document.addEventListener("DOMContentLoaded", () => {
  const modal = document.getElementById("case-allocate-modal");
  const openBtn = document.getElementById("open-allocate-modal");
  const closeBtn = document.getElementById("close-allocate-modal");
  const form = document.getElementById("case-allocate-form");
  const allocateAll = document.getElementById("id_allocate_to_all");
  const assignee = document.getElementById("id_assigned_to");
  const assigneeField = document.getElementById("allocate-employee-field");
  const assigneeRequired = document.getElementById("allocate-employee-required");
  const dueDate = document.getElementById("id_due_date");

  if (!modal || !openBtn) return;

  const syncAllocateMode = () => {
    const allSelected = Boolean(allocateAll?.checked);
    if (assignee) {
      assignee.disabled = allSelected;
      assignee.required = !allSelected;
      if (allSelected) {
        assignee.value = "";
      }
    }
    if (assigneeRequired) {
      assigneeRequired.hidden = allSelected;
    }
    if (assigneeField) {
      assigneeField.classList.toggle("is-disabled", allSelected);
    }
  };

  const openModal = () => {
    if (typeof modal.showModal === "function") {
      modal.showModal();
    } else {
      modal.setAttribute("open", "");
    }
    syncAllocateMode();
    window.setTimeout(() => {
      if (allocateAll?.checked) {
        allocateAll.focus();
      } else {
        assignee?.focus();
      }
    }, 0);
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
  allocateAll?.addEventListener("change", syncAllocateMode);

  modal.addEventListener("click", (event) => {
    if (event.target === modal) closeModal();
  });

  if (modal.hasAttribute("open") && typeof modal.showModal === "function") {
    // Re-open properly after validation errors (native dialog attribute alone is inconsistent)
    modal.removeAttribute("open");
    openModal();
  } else {
    syncAllocateMode();
  }

  form?.addEventListener("submit", (event) => {
    // Disabled fields are omitted from POST; re-enable before submit if needed.
    if (assignee) {
      assignee.disabled = false;
    }
    const allSelected = Boolean(allocateAll?.checked);
    if (!allSelected && !assignee?.value) {
      event.preventDefault();
      syncAllocateMode();
      assignee?.reportValidity?.();
      assignee?.focus();
      return;
    }
    if (!dueDate?.value) {
      event.preventDefault();
      syncAllocateMode();
      dueDate?.reportValidity?.();
      dueDate?.focus();
    }
  });
});
