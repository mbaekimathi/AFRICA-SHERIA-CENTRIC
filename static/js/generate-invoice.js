(() => {
  const form = document.getElementById("generate-invoice-form");
  if (!form) return;

  const linesWrap = document.getElementById("invoice-lines");
  const addLineBtn = document.getElementById("invoice-add-line");
  const taxEnabled = document.getElementById("invoice-tax-enabled");
  const taxRateWrap = document.getElementById("invoice-tax-rate-wrap");
  const taxRateInput = document.getElementById("invoice-tax-rate");
  const taxRow = document.getElementById("invoice-tax-row");
  const taxRateDisplay = document.getElementById("invoice-tax-rate-display");
  const taxDisplay = document.getElementById("invoice-tax-display");
  const subtotalEl = document.getElementById("invoice-subtotal");
  const totalEl = document.getElementById("invoice-total");

  const descriptionField = document.getElementById("id_invoice_description");
  const amountField = document.getElementById("id_invoice_amount");
  const taxAmountField = document.getElementById("id_invoice_tax_amount");

  let lineIndex = 1;

  function createLine() {
    const line = document.createElement("div");
    line.className = "invoice-line";
    line.dataset.lineIndex = String(lineIndex++);
    line.innerHTML = `
      <div class="invoice-line__fields">
        <div class="form-field invoice-line__desc">
          <label>Service description <span aria-hidden="true">*</span></label>
          <input type="text" class="form-input line-description" placeholder="e.g. Document drafting" required>
        </div>
        <div class="form-field invoice-line__amount">
          <label>Amount (KES) <span aria-hidden="true">*</span></label>
          <input type="number" class="form-input line-amount" min="0" step="0.01" placeholder="0.00" required>
        </div>
      </div>
      <button type="button" class="invoice-line__remove" title="Remove line" aria-label="Remove line item">
        <svg viewBox="0 0 24 24" width="18" height="18" fill="none">
          <path d="M18 6 6 18M6 6l12 12" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
        </svg>
      </button>
    `;
    linesWrap.appendChild(line);
    updateRemoveButtons();
    recalculate();
    line.querySelector(".line-description").focus();
  }

  function updateRemoveButtons() {
    const lines = linesWrap.querySelectorAll(".invoice-line");
    lines.forEach((line) => {
      const btn = line.querySelector(".invoice-line__remove");
      if (btn) btn.hidden = lines.length <= 1;
    });
  }

  function removeLine(line) {
    line.remove();
    updateRemoveButtons();
    recalculate();
  }

  function getLines() {
    const lines = [];
    linesWrap.querySelectorAll(".invoice-line").forEach((line) => {
      const desc = (line.querySelector(".line-description")?.value || "").trim();
      const amt = parseFloat(line.querySelector(".line-amount")?.value || "0") || 0;
      if (desc || amt > 0) {
        lines.push({ description: desc, amount: amt });
      }
    });
    return lines;
  }

  function recalculate() {
    const lines = getLines();
    const subtotal = lines.reduce((sum, l) => sum + l.amount, 0);
    const applyTax = taxEnabled.checked;
    const rate = parseFloat(taxRateInput.value) || 0;
    const taxAmt = applyTax ? subtotal * (rate / 100) : 0;
    const total = subtotal + taxAmt;

    subtotalEl.textContent = `KES ${subtotal.toFixed(2)}`;
    taxDisplay.textContent = `KES ${taxAmt.toFixed(2)}`;
    totalEl.textContent = `KES ${total.toFixed(2)}`;
    taxRateDisplay.textContent = rate % 1 === 0 ? String(Math.round(rate)) : rate.toFixed(2);

    taxRateWrap.hidden = !applyTax;
    taxRow.hidden = !applyTax;
  }

  function syncHiddenFields() {
    const lines = getLines();
    const descriptions = lines.map((l) => l.description).filter(Boolean);
    const subtotal = lines.reduce((sum, l) => sum + l.amount, 0);
    const applyTax = taxEnabled.checked;
    const rate = parseFloat(taxRateInput.value) || 0;
    const taxAmt = applyTax ? subtotal * (rate / 100) : 0;

    descriptionField.value = descriptions.join("\n");
    amountField.value = subtotal.toFixed(2);
    taxAmountField.value = taxAmt.toFixed(2);
  }

  addLineBtn.addEventListener("click", createLine);

  linesWrap.addEventListener("click", (e) => {
    const removeBtn = e.target.closest(".invoice-line__remove");
    if (!removeBtn) return;
    removeLine(removeBtn.closest(".invoice-line"));
  });

  linesWrap.addEventListener("input", recalculate);
  taxEnabled.addEventListener("change", recalculate);
  taxRateInput.addEventListener("input", recalculate);

  form.addEventListener("submit", (e) => {
    const lines = getLines();
    if (!lines.length || lines.every((l) => !l.description)) {
      e.preventDefault();
      alert("Add at least one service line item with a description.");
      return;
    }
    syncHiddenFields();
  });

  updateRemoveButtons();
  recalculate();
})();
