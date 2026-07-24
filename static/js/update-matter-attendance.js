(() => {
  function setupDynamicList({
    listId,
    addBtnId,
    templateId,
    totalFormsName,
    cardSelector,
    indexAttr,
  }) {
    const list = document.getElementById(listId);
    const addBtn = document.getElementById(addBtnId);
    const template = document.getElementById(templateId);
    const totalFormsInput = document.querySelector(
      `input[name="${totalFormsName}"]`
    );
    if (!list || !addBtn || !template || !totalFormsInput) {
      return null;
    }

    function visibleCards() {
      return Array.from(list.querySelectorAll(cardSelector)).filter((card) => {
        const del = card.querySelector('input[name$="-DELETE"]');
        return !(del && del.checked);
      });
    }

    function renumber() {
      visibleCards().forEach((card, index) => {
        const num = card.querySelector(".card-num");
        if (num) num.textContent = String(index + 1);
      });
    }

    function wireRemove(card) {
      const remove = card.querySelector(".party-card__remove");
      if (!remove || remove.dataset.wired === "true") return;
      remove.dataset.wired = "true";
      remove.addEventListener("click", (event) => {
        if (event.target.closest("input")) return;
        event.preventDefault();
        const del = card.querySelector('input[name$="-DELETE"]');
        if (!del) return;
        del.checked = true;
        card.hidden = true;
        renumber();
      });
    }

    function addCard(values = {}) {
      const index = Number(totalFormsInput.value);
      const html = template.innerHTML
        .replaceAll("__prefix__", String(index))
        .replaceAll("__num__", String(index + 1));
      const wrapper = document.createElement("div");
      wrapper.innerHTML = html.trim();
      const card = wrapper.firstElementChild;
      if (!card) return null;
      card.setAttribute(indexAttr, String(index));
      list.appendChild(card);
      totalFormsInput.value = String(index + 1);
      wireRemove(card);
      renumber();

      Object.entries(values).forEach(([name, value]) => {
        const field = card.querySelector(`[name$="-${name}"]`);
        if (!field || value === undefined || value === null) return;
        field.value = String(value);
      });

      return card;
    }

    function clearCards() {
      list.querySelectorAll(cardSelector).forEach((card) => card.remove());
      totalFormsInput.value = "0";
      const initialFormsInput = document.querySelector(
        `input[name="${totalFormsName.replace("TOTAL_FORMS", "INITIAL_FORMS")}"]`
      );
      if (initialFormsInput) initialFormsInput.value = "0";
      renumber();
    }

    list.querySelectorAll(cardSelector).forEach(wireRemove);
    renumber();

    addBtn.addEventListener("click", () => {
      const card = addCard();
      card?.querySelector("input, select, textarea")?.focus();
    });

    return { addCard, clearCards, renumber, list, totalFormsInput };
  }

  function syncVirtualLinkField(root) {
    if (!root) return;
    const attendanceSelect = root.querySelector("[data-virtual-toggle]");
    const linkField =
      root.querySelector("[data-virtual-link-field]") ||
      root.querySelector("#virtual-link-field");
    const linkInput =
      root.querySelector("[data-virtual-link]") ||
      (linkField ? linkField.querySelector('input[type="url"], input') : null);
    if (!attendanceSelect || !linkField) return;

    const isVirtual = attendanceSelect.value === "virtual";
    if (isVirtual) {
      linkField.hidden = false;
      linkField.removeAttribute("hidden");
      linkField.style.display = "";
      linkField.classList.remove("is-hidden");
    } else {
      linkField.hidden = true;
      linkField.setAttribute("hidden", "");
      linkField.style.display = "none";
      linkField.classList.add("is-hidden");
      if (linkInput) linkInput.value = "";
    }
  }

  function setupVirtualLinkToggle(root = document) {
    if (!root) return;
    const attendanceSelect = root.querySelector("[data-virtual-toggle]");
    if (!attendanceSelect) return;

    if (attendanceSelect.dataset.virtualWired !== "true") {
      attendanceSelect.dataset.virtualWired = "true";
      const onChange = () => {
        const scope = attendanceSelect.closest("form") || root;
        syncVirtualLinkField(scope);
      };
      attendanceSelect.addEventListener("change", onChange);
      attendanceSelect.addEventListener("input", onChange);
    }
    syncVirtualLinkField(attendanceSelect.closest("form") || root);
  }

  function parseAttendanceData() {
    const node = document.getElementById("previous-matter-attendances-data");
    if (!node) return {};
    try {
      const rows = JSON.parse(node.textContent || "[]");
      return Object.fromEntries(rows.map((row) => [String(row.id), row]));
    } catch (_error) {
      return {};
    }
  }

  function textOrDash(value) {
    const text = (value || "").toString().trim();
    return text || "—";
  }

  function setMultiline(el, value) {
    if (!el) return;
    el.textContent = "";
    const text = (value || "").toString().trim();
    if (!text) {
      el.textContent = "—";
      return;
    }
    text.split(/\r?\n/).forEach((line, index) => {
      if (index > 0) el.appendChild(document.createElement("br"));
      el.appendChild(document.createTextNode(line));
    });
  }

  function openDialog(modal) {
    if (!modal) return;
    if (typeof modal.showModal === "function") {
      if (!modal.open) modal.showModal();
    } else {
      modal.setAttribute("open", "");
    }
  }

  function closeDialog(modal) {
    if (!modal) return;
    if (typeof modal.close === "function") {
      modal.close();
    } else {
      modal.removeAttribute("open");
    }
  }

  function wireBackdropClose(modal, closeFn) {
    if (!modal) return;
    modal.addEventListener("click", (event) => {
      if (event.target === modal) closeFn();
    });
  }

  function fillViewModal(data) {
    const title = document.getElementById("view-matter-attendance-title");
    const lead = document.getElementById("view-matter-attendance-lead");
    const presence = document.getElementById("view-matter-attendance-presence");
    if (title) {
      title.textContent = data.activity_type || "Matter attendance";
    }
    if (lead) {
      lead.textContent = [data.attendance_date_display, data.contact_person]
        .filter(Boolean)
        .join(" · ");
    }
    if (presence) {
      presence.textContent = data.presence_display || "—";
      presence.className = `status-pill status-pill--${data.presence || "present"}`;
    }

    const setText = (id, value) => {
      const el = document.getElementById(id);
      if (el) el.textContent = textOrDash(value);
    };

    setText("view-matter-contact", data.contact_person);
    setText("view-matter-location", data.location);
    setText("view-matter-recorded-by", data.recorded_by);
    setMultiline(
      document.getElementById("view-matter-outcome"),
      data.outcome_notes
    );
    setMultiline(
      document.getElementById("view-matter-next-action"),
      data.next_action
    );

    const nextAppearance = data.next_attendance_date_display
      ? `${data.next_activity_type || "Matter"} · ${data.next_attendance_date_display}`
      : "";
    setText("view-matter-next-appearance", nextAppearance);
    setText("view-matter-next-contact", data.next_contact_person);
    setText(
      "view-matter-next-client",
      data.next_client_attendance_display
    );

    const virtualWrap = document.getElementById("view-matter-virtual-wrap");
    const virtualEl = document.getElementById("view-matter-virtual");
    if (virtualWrap && virtualEl) {
      if (data.next_client_attendance === "virtual") {
        virtualWrap.hidden = false;
        virtualEl.textContent = "";
        if (data.virtual_link) {
          const link = document.createElement("a");
          link.href = data.virtual_link;
          link.target = "_blank";
          link.rel = "noopener noreferrer";
          link.textContent = data.virtual_link;
          virtualEl.appendChild(link);
        } else {
          virtualEl.textContent = "—";
        }
      } else {
        virtualWrap.hidden = true;
      }
    }

    const quorumWrap = document.getElementById("view-matter-quorum-wrap");
    const quorumList = document.getElementById("view-matter-quorum");
    if (quorumWrap && quorumList) {
      quorumList.textContent = "";
      const members = data.quorum_members || [];
      if (members.length) {
        quorumWrap.hidden = false;
        members.forEach((member) => {
          const li = document.createElement("li");
          const strong = document.createElement("strong");
          strong.textContent = member.participant_name || "Participant";
          li.appendChild(strong);
          if (member.what_they_said) {
            li.appendChild(
              document.createTextNode(` — ${member.what_they_said}`)
            );
          }
          quorumList.appendChild(li);
        });
      } else {
        quorumWrap.hidden = true;
      }
    }

    const bringupsWrap = document.getElementById("view-matter-bringups-wrap");
    const bringupsList = document.getElementById("view-matter-bringups");
    if (bringupsWrap && bringupsList) {
      bringupsList.textContent = "";
      const items = data.bring_up_items || [];
      if (items.length) {
        bringupsWrap.hidden = false;
        items.forEach((item) => {
          const li = document.createElement("li");
          const parts = [item.description || ""];
          if (item.reminder_frequency_display) {
            parts.push(item.reminder_frequency_display);
          }
          if (item.allocated_to_name) {
            parts.push(item.allocated_to_name);
          }
          li.textContent = parts.filter(Boolean).join(" · ");
          bringupsList.appendChild(li);
        });
      } else {
        bringupsWrap.hidden = true;
      }
    }
  }

  function setFieldValue(form, name, value) {
    const field = form.querySelector(`[name="edit-${name}"]`);
    if (!field) return;
    field.value = value == null ? "" : String(value);
  }

  function fillEditModal(form, data, lists) {
    if (!form || !data) return;
    form.setAttribute("action", data.edit_url || "");

    const lead = document.getElementById("edit-matter-attendance-lead");
    if (lead) {
      lead.textContent = [data.activity_type, data.attendance_date_display]
        .filter(Boolean)
        .join(" · ");
    }

    setFieldValue(form, "activity_type", data.activity_type);
    setFieldValue(form, "contact_person", data.contact_person);
    setFieldValue(form, "location", data.location);
    setFieldValue(form, "attendance_date", data.attendance_date);
    setFieldValue(form, "presence", data.presence);
    setFieldValue(form, "outcome_notes", data.outcome_notes);
    setFieldValue(form, "next_action", data.next_action);
    setFieldValue(form, "next_activity_type", data.next_activity_type);
    setFieldValue(form, "next_attendance_date", data.next_attendance_date);
    setFieldValue(form, "next_contact_person", data.next_contact_person);
    setFieldValue(form, "next_client_attendance", data.next_client_attendance);
    setFieldValue(form, "virtual_link", data.virtual_link);

    if (lists.quorum) {
      lists.quorum.clearCards();
      const members = data.quorum_members || [];
      if (members.length) {
        members.forEach((member) => {
          lists.quorum.addCard({
            participant_name: member.participant_name || "",
            what_they_said: member.what_they_said || "",
          });
        });
      } else {
        lists.quorum.addCard();
      }
    }

    if (lists.bringups) {
      lists.bringups.clearCards();
      const items = data.bring_up_items || [];
      if (items.length) {
        items.forEach((item) => {
          lists.bringups.addCard({
            description: item.description || "",
            reminder_frequency: item.reminder_frequency || "",
            allocated_to: item.allocated_to || "",
          });
        });
      } else {
        lists.bringups.addCard();
      }
    }

    setupVirtualLinkToggle(form);
  }

  document.addEventListener("DOMContentLoaded", () => {
    setupDynamicList({
      listId: "quorum-list",
      addBtnId: "add-quorum-btn",
      templateId: "quorum-empty-form",
      totalFormsName: "quorum-TOTAL_FORMS",
      cardSelector: ".party-card",
      indexAttr: "data-quorum-index",
    });
    setupDynamicList({
      listId: "bringups-list",
      addBtnId: "add-bringup-btn",
      templateId: "bringup-empty-form",
      totalFormsName: "bringups-TOTAL_FORMS",
      cardSelector: ".party-card",
      indexAttr: "data-bringup-index",
    });

    const createForm = document.getElementById("matter-attendance-form");
    setupVirtualLinkToggle(createForm);

    document.addEventListener("change", (event) => {
      const select = event.target.closest?.("[data-virtual-toggle]");
      if (!select) return;
      syncVirtualLinkField(select.closest("form") || document);
    });

    const attendanceById = parseAttendanceData();
    let activeAttendanceId = null;

    const viewModal = document.getElementById("view-matter-attendance-modal");
    const editModal = document.getElementById("edit-matter-attendance-modal");
    const editForm = document.getElementById("edit-matter-attendance-form");
    const closeViewBtn = document.getElementById("close-view-matter-attendance");
    const closeEditBtn = document.getElementById("close-edit-matter-attendance");
    const viewToEditBtn = document.getElementById(
      "view-to-edit-matter-attendance"
    );

    const editQuorum = setupDynamicList({
      listId: "edit-quorum-list",
      addBtnId: "edit-add-quorum-btn",
      templateId: "edit-quorum-empty-form",
      totalFormsName: "edit-quorum-TOTAL_FORMS",
      cardSelector: ".party-card",
      indexAttr: "data-quorum-index",
    });
    const editBringups = setupDynamicList({
      listId: "edit-bringups-list",
      addBtnId: "edit-add-bringup-btn",
      templateId: "edit-bringup-empty-form",
      totalFormsName: "edit-bringups-TOTAL_FORMS",
      cardSelector: ".party-card",
      indexAttr: "data-bringup-index",
    });

    if (editForm) {
      setupVirtualLinkToggle(editForm);
    }

    const openView = (attendanceId) => {
      const data = attendanceById[String(attendanceId)];
      if (!data || !viewModal) return;
      activeAttendanceId = String(attendanceId);
      fillViewModal(data);
      openDialog(viewModal);
    };

    const openEdit = (attendanceId) => {
      const data = attendanceById[String(attendanceId)];
      if (!data || !editModal || !editForm) return;
      activeAttendanceId = String(attendanceId);
      fillEditModal(editForm, data, {
        quorum: editQuorum,
        bringups: editBringups,
      });
      openDialog(editModal);
      window.setTimeout(() => {
        editForm.querySelector("input, select, textarea")?.focus();
      }, 0);
    };

    document
      .querySelectorAll(".open-view-matter-attendance")
      .forEach((btn) => {
        btn.addEventListener("click", (event) => {
          event.preventDefault();
          openView(btn.dataset.attendanceId);
        });
      });

    document
      .querySelectorAll(".open-edit-matter-attendance")
      .forEach((btn) => {
        btn.addEventListener("click", (event) => {
          event.preventDefault();
          openEdit(btn.dataset.attendanceId);
        });
      });

    if (closeViewBtn) {
      closeViewBtn.addEventListener("click", () => closeDialog(viewModal));
    }
    if (closeEditBtn) {
      closeEditBtn.addEventListener("click", () => closeDialog(editModal));
    }
    wireBackdropClose(viewModal, () => closeDialog(viewModal));
    wireBackdropClose(editModal, () => closeDialog(editModal));

    if (viewToEditBtn) {
      viewToEditBtn.addEventListener("click", () => {
        closeDialog(viewModal);
        if (activeAttendanceId) openEdit(activeAttendanceId);
      });
    }

    if (editModal && editModal.hasAttribute("open")) {
      if (typeof editModal.showModal === "function") {
        editModal.removeAttribute("open");
        openDialog(editModal);
      }
      window.setTimeout(() => {
        editForm
          ?.querySelector(".field-error")
          ?.closest(".form-field")
          ?.querySelector("input, select, textarea")
          ?.focus();
      }, 0);
    }
  });
})();
