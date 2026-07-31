document.addEventListener("DOMContentLoaded", () => {
  const modal = document.getElementById("role-allocate-modal");
  const openBtn = document.getElementById("open-role-modal");
  const closeBtn = document.getElementById("close-role-modal");
  const roleSelect = document.getElementById("id_allocate_role");
  const form = document.getElementById("role-allocate-form");
  const failureModal = document.getElementById("work-email-failure-modal");
  const closeFailureBtn = document.getElementById("close-work-email-failure");

  const show = (dialog) => {
    if (!dialog) return;
    if (typeof dialog.showModal === "function") {
      dialog.showModal();
    } else {
      dialog.setAttribute("open", "");
    }
  };

  const hide = (dialog) => {
    if (!dialog) return;
    if (typeof dialog.close === "function") {
      dialog.close();
    } else {
      dialog.removeAttribute("open");
    }
  };

  const openModal = () => {
    show(modal);
    window.setTimeout(() => roleSelect?.focus(), 0);
  };

  const closeModal = () => hide(modal);

  if (failureModal) {
    show(failureModal);
    closeFailureBtn?.addEventListener("click", () => {
      hide(failureModal);
      const previousRole = failureModal.dataset.role || "";
      if (previousRole && roleSelect) roleSelect.value = previousRole;
      openModal();
    });
  }

  if (!modal || !openBtn) return;

  openBtn.addEventListener("click", openModal);
  closeBtn?.addEventListener("click", closeModal);

  modal.addEventListener("click", (event) => {
    if (event.target === modal) closeModal();
  });

  form?.addEventListener("submit", (event) => {
    if (!roleSelect?.value) {
      event.preventDefault();
      roleSelect?.reportValidity?.();
      roleSelect?.focus();
    }
  });
});
