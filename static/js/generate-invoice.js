(() => {
  const form = document.getElementById("generate-invoice-form");
  if (!form) return;

  const linesWrap = document.getElementById("invoice-lines");
  const addLineBtn = document.getElementById("invoice-add-line");
  const taxEnabled = document.getElementById("invoice-tax-enabled");
  const taxConfig = document.getElementById("invoice-tax-config");
  const taxProfile = document.getElementById("id_invoice_tax_profile");
  const taxPercentage = document.getElementById("id_invoice_tax_percentage");
  const registerTaxBtn = document.getElementById("invoice-register-tax");
  const cancelNewTaxBtn = document.getElementById("invoice-cancel-new-tax");
  const newTaxPanel = document.getElementById("invoice-new-tax");
  const newTaxName = document.getElementById("id_invoice_new_tax_name");
  const newTaxRate = document.getElementById("id_invoice_new_tax_rate");
  const taxRow = document.getElementById("invoice-tax-row");
  const taxNameDisplay = document.getElementById("invoice-tax-name-display");
  const taxRateDisplay = document.getElementById("invoice-tax-rate-display");
  const taxDisplay = document.getElementById("invoice-tax-display");
  const subtotalEl = document.getElementById("invoice-subtotal");
  const totalEl = document.getElementById("invoice-total");
  const itemCountEl = document.getElementById("invoice-item-count");
  const linesError = document.getElementById("invoice-lines-error");

  const descriptionField = document.getElementById("id_invoice_description");
  const amountField = document.getElementById("id_invoice_amount");
  const taxAmountField = document.getElementById("id_invoice_tax_amount");

  let lineIndex = 1;

  const money = new Intl.NumberFormat("en-KE", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

  const SERVICE_MARKER = "[SERVICE]";
  const AMOUNT_MARKER = "[AMOUNT]";
  let registeringNewTax = Boolean(newTaxName?.value || newTaxRate?.value);

  function selectedTaxData() {
    if (registeringNewTax) {
      return {
        name: (newTaxName?.value || "").trim() || "Tax",
        rate: parseFloat(newTaxRate?.value || "0") || 0,
        defaultRate: parseFloat(newTaxRate?.value || "0") || 0,
      };
    }

    const option = taxProfile?.selectedOptions?.[0];
    const defaultRate = parseFloat(option?.dataset?.rate || "0") || 0;
    const name = (option?.dataset?.name || "").trim()
      || (option?.textContent || "").replace(/\s*[—-]\s*[\d.]+%\s*$/, "").trim()
      || "Tax";
    return {
      name,
      rate: parseFloat(taxPercentage?.value || String(defaultRate)) || 0,
      defaultRate,
    };
  }

  function fillPercentageFromSelection() {
    if (registeringNewTax) return;
    const option = taxProfile?.selectedOptions?.[0];
    if (!option || !option.value) {
      taxPercentage.value = "";
      return;
    }
    taxPercentage.value = option.dataset.rate || "";
  }

  function setNewTaxMode(enabled) {
    registeringNewTax = enabled;
    newTaxPanel.hidden = !enabled;
    registerTaxBtn.hidden = enabled;
    const taxPick = document.querySelector(".gen-inv__tax-pick");
    const taxHint = document.querySelector(".gen-inv__tax-hint");
    if (taxPick) taxPick.hidden = enabled;
    if (taxHint) taxHint.hidden = enabled;
    if (enabled) {
      taxProfile.value = "";
      taxPercentage.value = "";
      newTaxName?.focus();
    } else {
      newTaxName.value = "";
      newTaxRate.value = "";
    }
    recalculate();
  }

  function detailRowHtml() {
    return `
      <div class="invoice-service__detail">
        <span class="invoice-service__bullet" aria-hidden="true">•</span>
        <input type="text" class="form-input line-detail" placeholder="e.g. Contract review and amendments">
        <button type="button" class="invoice-service__detail-remove" title="Remove detail" aria-label="Remove detail">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none">
            <path d="M18 6 6 18M6 6l12 12" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
          </svg>
        </button>
      </div>
    `;
  }

  function serviceCardHtml(index) {
    return `
      <div class="invoice-service__top">
        <span class="invoice-service__badge">Service ${index + 1}</span>
        <button type="button" class="invoice-service__remove" title="Remove service" aria-label="Remove service">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none">
            <path d="M18 6 6 18M6 6l12 12" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
          </svg>
          Remove
        </button>
      </div>

      <div class="invoice-service__grid">
        <div class="form-field invoice-service__title-field">
          <label>Service title <span aria-hidden="true">*</span></label>
          <input type="text" class="form-input line-title" placeholder="e.g. Legal advisory & drafting" required>
        </div>
        <div class="form-field invoice-service__amount-field">
          <label>Amount (KES)</label>
          <div class="gen-inv__money">
            <span class="gen-inv__money-prefix">KES</span>
            <input type="number" class="form-input line-amount" min="0" step="0.01" placeholder="0.00">
          </div>
        </div>
      </div>

      <div class="invoice-service__details">
        <div class="invoice-service__details-label">Details <span class="gen-inv__optional">(optional)</span></div>
        <div class="invoice-service__detail-list">
          ${detailRowHtml()}
        </div>
        <button type="button" class="invoice-service__add-detail">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" aria-hidden="true">
            <path d="M12 5v14M5 12h14" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
          </svg>
          Add detail
        </button>
      </div>
    `;
  }

  function createService() {
    const service = document.createElement("div");
    service.className = "invoice-service";
    service.dataset.lineIndex = String(lineIndex++);
    service.innerHTML = serviceCardHtml(
      linesWrap.querySelectorAll(".invoice-service").length
    );
    linesWrap.appendChild(service);
    refreshServiceUi();
    recalculate();
    service.querySelector(".line-title")?.focus();
  }

  function addDetail(service) {
    const list = service.querySelector(".invoice-service__detail-list");
    if (!list) return;
    list.insertAdjacentHTML("beforeend", detailRowHtml());
    refreshDetailButtons(service);
    const inputs = list.querySelectorAll(".line-detail");
    inputs[inputs.length - 1]?.focus();
  }

  function refreshDetailButtons(service) {
    const details = service.querySelectorAll(".invoice-service__detail");
    details.forEach((row) => {
      const btn = row.querySelector(".invoice-service__detail-remove");
      if (btn) btn.hidden = details.length <= 1;
    });
  }

  function refreshServiceUi() {
    const services = linesWrap.querySelectorAll(".invoice-service");
    services.forEach((service, index) => {
      const badge = service.querySelector(".invoice-service__badge");
      if (badge) badge.textContent = `Service ${index + 1}`;
      const removeBtn = service.querySelector(".invoice-service__remove");
      if (removeBtn) removeBtn.hidden = services.length <= 1;
      refreshDetailButtons(service);
    });
  }

  function removeService(service) {
    service.remove();
    refreshServiceUi();
    recalculate();
  }

  function getServices() {
    const services = [];
    linesWrap.querySelectorAll(".invoice-service").forEach((service) => {
      const title = (service.querySelector(".line-title")?.value || "").trim();
      const amount =
        parseFloat(service.querySelector(".line-amount")?.value || "0") || 0;
      const details = [];
      service.querySelectorAll(".line-detail").forEach((input) => {
        const value = (input.value || "").trim();
        if (value) details.push(value);
      });
      if (title || amount > 0 || details.length) {
        services.push({ title, amount, details });
      }
    });
    return services;
  }

  function formatServices(services) {
    return services
      .filter((service) => service.title)
      .map((service) => {
        const lines = [
          `${SERVICE_MARKER} ${service.title}`,
          `${AMOUNT_MARKER} ${service.amount.toFixed(2)}`,
        ];
        service.details.forEach((detail) => lines.push(`- ${detail}`));
        return lines.join("\n");
      })
      .join("\n\n");
  }

  function recalculate() {
    const services = getServices().filter((service) => service.title);
    const subtotal = services.reduce((sum, service) => sum + service.amount, 0);
    const applyTax = taxEnabled.checked;
    const tax = selectedTaxData();
    const rate = tax.rate;
    const taxAmt = applyTax ? subtotal * (rate / 100) : 0;
    const total = subtotal + taxAmt;

    subtotalEl.textContent = `KES ${money.format(subtotal)}`;
    taxDisplay.textContent = `KES ${money.format(taxAmt)}`;
    totalEl.textContent = `KES ${money.format(total)}`;
    taxRateDisplay.textContent =
      rate % 1 === 0 ? String(Math.round(rate)) : rate.toFixed(2);
    taxNameDisplay.textContent = tax.name;
    if (itemCountEl) itemCountEl.textContent = String(services.length);

    taxConfig.hidden = !applyTax;
    taxRow.hidden = !applyTax;
  }

  function syncHiddenFields() {
    const services = getServices().filter((service) => service.title);
    const subtotal = services.reduce((sum, service) => sum + service.amount, 0);
    const applyTax = taxEnabled.checked;
    const rate = selectedTaxData().rate;
    const taxAmt = applyTax ? subtotal * (rate / 100) : 0;

    descriptionField.value = formatServices(services);
    amountField.value = subtotal.toFixed(2);
    taxAmountField.value = taxAmt.toFixed(2);
    if (!applyTax) {
      taxProfile.value = "";
      taxPercentage.value = "";
      newTaxName.value = "";
      newTaxRate.value = "";
    }
  }

  addLineBtn.addEventListener("click", createService);

  linesWrap.addEventListener("click", (e) => {
    const addDetailBtn = e.target.closest(".invoice-service__add-detail");
    if (addDetailBtn) {
      addDetail(addDetailBtn.closest(".invoice-service"));
      return;
    }

    const removeDetailBtn = e.target.closest(".invoice-service__detail-remove");
    if (removeDetailBtn) {
      const service = removeDetailBtn.closest(".invoice-service");
      const row = removeDetailBtn.closest(".invoice-service__detail");
      const list = service?.querySelector(".invoice-service__detail-list");
      if (list && list.querySelectorAll(".invoice-service__detail").length > 1) {
        row.remove();
        refreshDetailButtons(service);
      }
      return;
    }

    const removeServiceBtn = e.target.closest(".invoice-service__remove");
    if (removeServiceBtn) {
      removeService(removeServiceBtn.closest(".invoice-service"));
    }
  });

  linesWrap.addEventListener("input", () => {
    if (linesError) linesError.hidden = true;
    recalculate();
  });
  linesWrap.addEventListener("keydown", (e) => {
    if (e.key !== "Enter" || !e.target.matches(".line-detail")) return;
    e.preventDefault();
    addDetail(e.target.closest(".invoice-service"));
  });
  taxEnabled.addEventListener("change", () => {
    if (taxEnabled.checked && !taxProfile.value && !registeringNewTax) {
      // Prefer the first registered tax so the dropdown is immediately useful.
      const first = Array.from(taxProfile.options).find((opt) => opt.value);
      if (first) {
        taxProfile.value = first.value;
        fillPercentageFromSelection();
      }
    }
    recalculate();
  });
  taxProfile.addEventListener("change", () => {
    if (taxProfile.value) setNewTaxMode(false);
    fillPercentageFromSelection();
    recalculate();
  });
  taxPercentage.addEventListener("input", () => {
    // Keep the selected option's displayed rate label in sync while editing.
    const option = taxProfile?.selectedOptions?.[0];
    if (option?.value && option.dataset.name) {
      const rate = parseFloat(taxPercentage.value || "0") || 0;
      const rateText = rate % 1 === 0 ? String(Math.round(rate)) : rate.toFixed(2);
      option.dataset.rate = String(rate);
      option.textContent = `${option.dataset.name} - ${rateText}%`;
    }
    recalculate();
  });
  newTaxName.addEventListener("input", recalculate);
  newTaxRate.addEventListener("input", recalculate);
  registerTaxBtn.addEventListener("click", () => setNewTaxMode(true));
  cancelNewTaxBtn.addEventListener("click", () => setNewTaxMode(false));

  form.addEventListener("submit", (e) => {
    const services = getServices().filter((service) => service.title);
    if (!services.length) {
      e.preventDefault();
      if (linesError) {
        linesError.hidden = false;
        linesError.scrollIntoView({ behavior: "smooth", block: "center" });
      }
      linesWrap.querySelector(".line-title")?.focus();
      return;
    }
    if (taxEnabled.checked && !registeringNewTax && !taxProfile.value) {
      e.preventDefault();
      taxConfig.hidden = false;
      taxProfile.focus();
      return;
    }
    if (linesError) linesError.hidden = true;
    syncHiddenFields();
  });

  refreshServiceUi();
  if (taxProfile.value || registeringNewTax) {
    taxEnabled.checked = true;
  }
  setNewTaxMode(registeringNewTax);
  if (taxProfile.value && !taxPercentage.value) {
    fillPercentageFromSelection();
  }
  recalculate();
})();
