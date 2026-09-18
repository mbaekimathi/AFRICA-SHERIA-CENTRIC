document.addEventListener("DOMContentLoaded", () => {
  const modal = document.getElementById("case-allocate-modal");
  const openBtn = document.getElementById("open-allocate-modal");
  const closeBtn = document.getElementById("close-allocate-modal");
  const form = document.getElementById("case-allocate-form");
  const list = document.querySelector("#allocate-employee-field .allocate-employee-list");
  const dueDate = document.getElementById("id_due_date");
  const ALL_VALUE = "__all__";

  if (!modal || !openBtn) return;

  const getChecks = () =>
    Array.from(list?.querySelectorAll('input[type="checkbox"][name="assigned_to"]') || []);

  const syncAllocateMode = () => {
    const checks = getChecks();
    const allBox = checks.find((input) => input.value === ALL_VALUE);
    const personBoxes = checks.filter((input) => input.value !== ALL_VALUE);
    const allSelected = Boolean(allBox?.checked);

    personBoxes.forEach((input) => {
      input.disabled = allSelected;
      if (allSelected) input.checked = false;
    });
  };

  const openModal = () => {
    if (typeof modal.showModal === "function") {
      modal.showModal();
    } else {
      modal.setAttribute("open", "");
    }
    syncAllocateMode();
    window.setTimeout(() => {
      getChecks()[0]?.focus();
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

  modal.addEventListener("click", (event) => {
    if (event.target === modal) closeModal();
  });

  list?.addEventListener("change", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLInputElement) || target.type !== "checkbox") {
      return;
    }
    if (target.value === ALL_VALUE && target.checked) {
      getChecks()
        .filter((input) => input.value !== ALL_VALUE)
        .forEach((input) => {
          input.checked = false;
        });
    } else if (target.value !== ALL_VALUE && target.checked) {
      const allBox = getChecks().find((input) => input.value === ALL_VALUE);
      if (allBox) allBox.checked = false;
    }
    syncAllocateMode();
  });

  if (modal.hasAttribute("open") && typeof modal.showModal === "function") {
    // Re-open properly after validation errors (native dialog attribute alone is inconsistent)
    modal.removeAttribute("open");
    openModal();
  } else {
    syncAllocateMode();
  }

  form?.addEventListener("submit", (event) => {
    // Disabled fields are omitted from POST; re-enable people boxes before submit.
    getChecks().forEach((input) => {
      input.disabled = false;
    });

    const selected = getChecks().filter((input) => input.checked);
    if (!selected.length) {
      event.preventDefault();
      syncAllocateMode();
      getChecks()[0]?.focus();
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
