document.addEventListener("DOMContentLoaded", () => {
  const modal = document.getElementById("role-allocate-modal");
  const openBtn = document.getElementById("open-role-modal");
  const closeBtn = document.getElementById("close-role-modal");
  const roleSelect = document.getElementById("id_allocate_role");
  const form = document.getElementById("role-allocate-form");

  if (!modal || !openBtn) return;

  const openModal = () => {
    if (typeof modal.showModal === "function") {
      modal.showModal();
    } else {
      modal.setAttribute("open", "");
    }
    window.setTimeout(() => roleSelect?.focus(), 0);
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

  form?.addEventListener("submit", (event) => {
    if (!roleSelect?.value) {
      event.preventDefault();
      roleSelect?.reportValidity?.();
      roleSelect?.focus();
    }
  });
});
