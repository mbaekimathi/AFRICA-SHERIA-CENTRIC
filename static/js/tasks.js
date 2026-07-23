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

    if (!modal || !form) return;

    const openModal = (dataset = {}) => {
      const url = dataset.url;
      if (url) form.setAttribute("action", url);
      if (subjectEl && subjectFrom) {
        subjectEl.textContent = subjectFrom(dataset);
      }
      if (typeof onOpen === "function") onOpen(dataset);
      if (typeof modal.showModal === "function") {
        if (!modal.open) modal.showModal();
      } else {
        modal.setAttribute("open", "");
      }
      window.setTimeout(() => {
        if (focusEl) focusEl.focus();
      }, 0);
    };

    const closeModal = () => {
      if (typeof modal.close === "function") {
        modal.close();
      } else {
        modal.removeAttribute("open");
      }
    };

    document.querySelectorAll(openSelector).forEach((btn) => {
      btn.addEventListener("click", (event) => {
        event.preventDefault();
        openModal({
          url: btn.dataset.acceptUrl || btn.dataset.rejectUrl,
          subject: btn.dataset.taskSubject || "",
          due: btn.dataset.taskDue || "",
        });
      });
    });

    if (closeBtn) closeBtn.addEventListener("click", closeModal);
    modal.addEventListener("click", (event) => {
      if (event.target === modal) closeModal();
    });

    if (modal.hasAttribute("open") && typeof modal.showModal === "function") {
      modal.removeAttribute("open");
      openModal({
        url: form.getAttribute("action") || "",
        subject: subjectEl ? subjectEl.textContent || "" : "",
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

  const rejectForm = document.getElementById("task-reject-form");
  if (rejectForm) {
    rejectForm.addEventListener("submit", (event) => {
      const value = ((rejectReason && rejectReason.value) || "").trim();
      if (value.length < 5) {
        event.preventDefault();
        if (rejectReason && rejectReason.reportValidity) {
          rejectReason.reportValidity();
        }
        if (rejectReason) rejectReason.focus();
      }
    });
  }

  const viewModal = document.getElementById("task-view-modal");
  const viewCloseBtn = document.getElementById("close-view-modal");
  const viewKicker = document.getElementById("task-view-title");
  const viewTitle = document.getElementById("task-view-task-title");
  const viewSubject = document.getElementById("task-view-subject");
  const viewEntity = document.getElementById("task-view-entity");
  const viewEntityFieldLabel = document.getElementById(
    "task-view-entity-field-label"
  );
  const viewMeta = document.getElementById("task-view-meta");
  const viewDue = document.getElementById("task-view-due");
  const viewBy = document.getElementById("task-view-by");
  const viewReminderWrap = document.getElementById("task-view-reminder-wrap");
  const viewReminder = document.getElementById("task-view-reminder");
  const viewInstructions = document.getElementById("task-view-instructions");
  const viewStatusPill = document.getElementById("task-view-status-pill");
  const viewEntityLink = document.getElementById("task-view-entity-link");
  const viewEntityLinkLabel = document.getElementById(
    "task-view-entity-link-label"
  );
  const viewCompleteForm = document.getElementById("task-view-complete-form");
  const viewCompleteNext = document.getElementById("task-view-complete-next");

  const setText = (el, value) => {
    if (el) el.textContent = value || "—";
  };

  const withTaskQuery = (url, taskId) => {
    if (!url || url === "#") return "";
    if (!taskId) return url;
    try {
      const parsed = new URL(url, window.location.origin);
      parsed.searchParams.set("task", String(taskId));
      return `${parsed.pathname}${parsed.search}${parsed.hash}`;
    } catch (err) {
      const base = url.split("#")[0];
      const hash = url.includes("#") ? `#${url.split("#").slice(1).join("#")}` : "";
      if (/([?&])task=/.test(base)) {
        return `${base.replace(/([?&])task=[^&]*/, `$1task=${taskId}`)}${hash}`;
      }
      return `${base}${base.includes("?") ? "&" : "?"}task=${taskId}${hash}`;
    }
  };

  const goToEntity = (url) => {
    if (!url || url === "#") return;
    window.location.assign(url);
  };

  const openViewModal = (trigger) => {
    if (!viewModal || !trigger) return false;

    const dataset = trigger.dataset || {};
    const kind = dataset.taskKind || "case";
    const kindNoun = kind === "matter" ? "matter" : "case";
    const entityLabel =
      dataset.entityLabel || (kind === "matter" ? "Open matter" : "Open case");
    const taskId = dataset.taskId || "";
    const entityUrl = withTaskQuery(
      dataset.entityUrl || trigger.getAttribute("href") || "",
      taskId
    );
    const payload = dataset.payloadId
      ? document.getElementById(dataset.payloadId)
      : null;

    setText(
      viewKicker,
      kind === "matter" ? "Your matter task" : "Your case task"
    );
    setText(viewEntityFieldLabel, kind === "matter" ? "Matter" : "Case");
    setText(viewTitle, dataset.taskTitle || "Task");
    setText(
      viewSubject,
      dataset.taskSubject
        ? `${dataset.taskSubject} — review the brief, open the ${kindNoun}, then submit when done.`
        : `Review the brief, open the ${kindNoun}, then submit when done.`
    );
    setText(viewMeta, dataset.taskMeta || "—");
    setText(viewDue, dataset.taskDueLabel || "—");
    setText(viewBy, dataset.taskBy || "—");

    if (viewEntity) {
      const entityText = dataset.taskSubject || "—";
      viewEntity.textContent = entityText;
      if (entityUrl) {
        viewEntity.href = entityUrl;
        viewEntity.dataset.navUrl = entityUrl;
        viewEntity.classList.remove("is-disabled");
        viewEntity.removeAttribute("aria-disabled");
        viewEntity.removeAttribute("tabindex");
      } else {
        viewEntity.removeAttribute("href");
        delete viewEntity.dataset.navUrl;
        viewEntity.classList.add("is-disabled");
        viewEntity.setAttribute("aria-disabled", "true");
        viewEntity.setAttribute("tabindex", "-1");
      }
    }

    if (viewReminderWrap && viewReminder) {
      if (dataset.taskReminder) {
        viewReminderWrap.hidden = false;
        setText(viewReminder, dataset.taskReminder);
      } else {
        viewReminderWrap.hidden = true;
        setText(viewReminder, "—");
      }
    }

    if (viewInstructions) {
      viewInstructions.innerHTML = payload
        ? payload.innerHTML || "No additional instructions."
        : "No additional instructions.";
    }

    if (viewStatusPill) {
      viewStatusPill.textContent = dataset.taskStatus || "Accepted";
      viewStatusPill.className = `status-pill status-pill--${
        dataset.taskStatusSlug || "accepted"
      }`;
    }

    if (viewEntityLink) {
      viewEntityLink.href = entityUrl || "#";
      viewEntityLink.hidden = !entityUrl;
      viewEntityLink.dataset.navUrl = entityUrl || "";
    }
    if (viewEntityLinkLabel) {
      viewEntityLinkLabel.textContent = entityLabel;
    }

    if (viewCompleteForm) {
      viewCompleteForm.setAttribute("action", dataset.completeUrl || "");
    }
    if (viewCompleteNext) {
      viewCompleteNext.value = `${window.location.pathname}${window.location.search}`;
    }

    try {
      if (typeof viewModal.showModal === "function") {
        if (!viewModal.open) viewModal.showModal();
      } else {
        viewModal.setAttribute("open", "");
      }
      return true;
    } catch (err) {
      return false;
    }
  };

  const closeViewModal = () => {
    if (!viewModal) return;
    if (typeof viewModal.close === "function") {
      viewModal.close();
    } else {
      viewModal.removeAttribute("open");
    }
  };

  document.addEventListener("click", (event) => {
    const trigger = event.target.closest(".open-view-modal");
    if (!trigger) return;
    event.preventDefault();
    openViewModal(trigger);
  });

  const onEntityNavClick = (event) => {
    const link = event.target.closest(
      "#task-view-entity-link, #task-view-entity"
    );
    if (!link || link.classList.contains("is-disabled")) return;
    const url = link.dataset.navUrl || link.getAttribute("href") || "";
    if (!url || url === "#") return;
    event.preventDefault();
    goToEntity(url);
  };

  if (viewEntityLink) {
    viewEntityLink.addEventListener("click", onEntityNavClick);
  }
  if (viewEntity) {
    viewEntity.addEventListener("click", onEntityNavClick);
  }

  if (viewCloseBtn) viewCloseBtn.addEventListener("click", closeViewModal);
  if (viewModal) {
    viewModal.addEventListener("click", (event) => {
      if (event.target === viewModal) closeViewModal();
    });
  }

  if (viewModal && viewModal.hasAttribute("open")) {
    const highlightedBtn = document.querySelector(
      ".task-row--highlight .open-view-modal"
    );
    const sourceBtn =
      highlightedBtn || document.querySelector(".open-view-modal");
    viewModal.removeAttribute("open");
    if (sourceBtn) openViewModal(sourceBtn);
  }
});
