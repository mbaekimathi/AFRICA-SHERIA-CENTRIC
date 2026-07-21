(() => {
  const modal = document.getElementById("access-denied-modal");
  if (!modal) return;

  const close = () => {
    if (typeof modal.close === "function") {
      modal.close();
    } else {
      modal.removeAttribute("open");
    }
  };

  const open = () => {
    if (typeof modal.showModal === "function" && !modal.open) {
      modal.showModal();
    } else {
      modal.setAttribute("open", "");
    }
  };

  document
    .getElementById("close-access-denied-modal")
    ?.addEventListener("click", close);
  document
    .getElementById("ack-access-denied-modal")
    ?.addEventListener("click", close);

  modal.addEventListener("click", (event) => {
    if (event.target === modal) close();
  });

  modal.addEventListener("cancel", (event) => {
    event.preventDefault();
    close();
  });

  open();
})();
