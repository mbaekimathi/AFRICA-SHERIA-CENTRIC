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
    if (!list || !addBtn || !template || !totalFormsInput) return;

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

    list.querySelectorAll(cardSelector).forEach(wireRemove);
    renumber();

    addBtn.addEventListener("click", () => {
      const index = Number(totalFormsInput.value);
      const html = template.innerHTML
        .replaceAll("__prefix__", String(index))
        .replaceAll("__num__", String(index + 1));
      const wrapper = document.createElement("div");
      wrapper.innerHTML = html.trim();
      const card = wrapper.firstElementChild;
      if (!card) return;
      card.setAttribute(indexAttr, String(index));
      list.appendChild(card);
      totalFormsInput.value = String(index + 1);
      wireRemove(card);
      renumber();
      card.querySelector("input, select, textarea")?.focus();
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    setupDynamicList({
      listId: "advocates-list",
      addBtnId: "add-advocate-btn",
      templateId: "advocate-empty-form",
      totalFormsName: "advocates-TOTAL_FORMS",
      cardSelector: ".party-card",
      indexAttr: "data-advocate-index",
    });
    setupDynamicList({
      listId: "bringups-list",
      addBtnId: "add-bringup-btn",
      templateId: "bringup-empty-form",
      totalFormsName: "bringups-TOTAL_FORMS",
      cardSelector: ".party-card",
      indexAttr: "data-bringup-index",
    });
  });
})();
