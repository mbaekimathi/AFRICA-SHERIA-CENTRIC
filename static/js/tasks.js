document.addEventListener("DOMContentLoaded", () => {
  const highlight = document.querySelector(".task-row--highlight");
  if (highlight) {
    highlight.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  const wireModal = ({
    modalId,
    formId,
    closeBtnId,
    openSelector,
    subjectElId,
    focusId,
    subjectFrom,
    onOpen,
  }) => {
    const modal = document.getElementById(modalId);
    const form = document.getElementById(formId);
    const closeBtn = document.getElementById(closeBtnId);
    const subjectEl = document.getElementById(subjectElId);
    const focusEl = focusId ? document.getElementById(focusId) : null;
    const openButtons = document.querySelectorAll(openSelector);

    if (!modal || !form) return;

    const openModal = (dataset = {}) => {
      const url = dataset.url;
      if (url) form.setAttribute("action", url);
      if (subjectEl && subjectFrom) {
        subjectEl.textContent = subjectFrom(dataset);
      }
      onOpen?.(dataset);
      if (typeof modal.showModal === "function") {
        modal.showModal();
      } else {
        modal.setAttribute("open", "");
      }
      window.setTimeout(() => focusEl?.focus(), 0);
    };

    const closeModal = () => {
      if (typeof modal.close === "function") {
        modal.close();
      } else {
        modal.removeAttribute("open");
      }
    };

    openButtons.forEach((btn) => {
      btn.addEventListener("click", () => {
        openModal({
          url: btn.dataset.acceptUrl || btn.dataset.rejectUrl,
          subject: btn.dataset.taskSubject || "",
          due: btn.dataset.taskDue || "",
        });
      });
    });

    closeBtn?.addEventListener("click", closeModal);
    modal.addEventListener("click", (event) => {
      if (event.target === modal) closeModal();
    });

    if (modal.hasAttribute("open") && typeof modal.showModal === "function") {
      modal.removeAttribute("open");
      openModal({
        url: form.getAttribute("action") || "",
        subject: subjectEl?.textContent || "",
        due: "",
      });
    }
  };

  wireModal({
    modalId: "task-accept-modal",
    formId: "task-accept-form",
    closeBtnId: "close-accept-modal",
    openSelector: ".open-accept-modal",
    subjectElId: "task-accept-subject",
    focusId: "id_accept_reminder_at",
    subjectFrom: ({ subject }) =>
      subject
        ? `Accept: ${subject}`
        : "Confirm acceptance. You can optionally set a personal reminder.",
  });

  const rejectReason = document.getElementById("id_reject_reason");
  wireModal({
    modalId: "task-reject-modal",
    formId: "task-reject-form",
    closeBtnId: "close-reject-modal",
    openSelector: ".open-reject-modal",
    subjectElId: "task-reject-subject",
    focusId: "id_reject_reason",
    subjectFrom: ({ subject }) =>
      subject
        ? `Provide a reason for rejecting: ${subject}`
        : "Provide a reason for rejecting this task. The person who tasked you will be notified.",
  });

  document.getElementById("task-reject-form")?.addEventListener("submit", (event) => {
    const value = (rejectReason?.value || "").trim();
    if (value.length < 5) {
      event.preventDefault();
      rejectReason?.reportValidity?.();
      rejectReason?.focus();
    }
  });
});
