document.addEventListener("DOMContentLoaded", () => {
  const modal = document.getElementById("live-task-modal");
  const fab = document.getElementById("open-live-task-modal");
  const closeBtn = document.getElementById("close-live-task-modal");
  const openBtns = document.querySelectorAll(".open-live-task-modal");

  if (!modal) return;

  // Re-parent the FAB to <body> so position:fixed is viewport-relative
  // (ancestor transform / overflow:clip otherwise makes it scroll with content).
  if (fab && fab.parentElement !== document.body) {
    document.body.appendChild(fab);
  }

  const openModal = () => {
    if (typeof modal.showModal === "function") {
      if (!modal.open) modal.showModal();
    } else {
      modal.setAttribute("open", "");
    }
  };

  const closeModal = () => {
    if (typeof modal.close === "function") {
      modal.close();
    } else {
      modal.removeAttribute("open");
    }
  };

  openBtns.forEach((btn) => {
    btn.addEventListener("click", (event) => {
      event.preventDefault();
      openModal();
    });
  });
  closeBtn?.addEventListener("click", closeModal);
  modal.addEventListener("click", (event) => {
    if (event.target === modal) closeModal();
  });
});
