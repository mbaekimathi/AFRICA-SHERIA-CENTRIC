(function () {
  "use strict";

  function q(value) {
    const amount = Number.parseFloat(String(value || "").replace(/,/g, ""));
    return Number.isFinite(amount) ? Math.round(amount * 100) / 100 : 0;
  }

  function formatMoney(value) {
    return `KES ${q(value).toLocaleString("en-KE", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })}`;
  }

  function parseJsonDataset(form, key, fallback) {
    try {
      return JSON.parse(form.dataset[key] || "");
    } catch (_error) {
      return fallback;
    }
  }

  function fieldValue(id) {
    const input = document.getElementById(id);
    return input ? q(input.value) : 0;
  }

  function calculateNssf(gross, employeeRate, employerRate, tier1Limit, pensionableCap) {
    const pensionable = Math.min(q(gross), q(pensionableCap));
    const tier1Base = Math.min(pensionable, q(tier1Limit));
    const tier2Base = Math.max(pensionable - q(tier1Limit), 0);
    const employeeAmount = q(
      (tier1Base * q(employeeRate)) / 100 + (tier2Base * q(employeeRate)) / 100
    );
    const employerAmount = q(
      (tier1Base * q(employerRate)) / 100 + (tier2Base * q(employerRate)) / 100
    );
    return { employeeAmount, employerAmount };
  }

  function calculatePercentage(base, rate) {
    return q((q(base) * q(rate)) / 100);
  }

  function calculatePaye(taxableIncome, settings) {
    const income = q(taxableIncome);
    if (income <= 0) return 0;

    const bands = [
      [q(settings.paye_band_1_max), q(settings.paye_band_1_rate)],
      [q(settings.paye_band_2_max), q(settings.paye_band_2_rate)],
      [q(settings.paye_band_3_max), q(settings.paye_band_3_rate)],
      [null, q(settings.paye_band_4_rate)],
    ];

    let tax = 0;
    let lower = 0;
    bands.forEach(([upper, rate]) => {
      if (income <= lower) return;
      const bracket = upper === null ? income - lower : Math.min(income, upper) - lower;
      if (bracket > 0) tax += (bracket * rate) / 100;
      if (upper !== null) lower = upper;
    });

    return Math.max(q(tax - q(settings.paye_personal_relief)), 0);
  }

  function sumEarnings() {
    return q(
      fieldValue("id_payroll_basic_salary") +
        fieldValue("id_payroll_house_allowance") +
        fieldValue("id_payroll_transport_allowance") +
        fieldValue("id_payroll_medical_allowance") +
        fieldValue("id_payroll_other_allowances") +
        fieldValue("id_payroll_bonuses_overtime_commissions")
    );
  }

  function readRateSettings() {
    return {
      nssf_employee_rate: fieldValue("id_payroll_nssf_employee_rate"),
      nssf_employer_rate: fieldValue("id_payroll_nssf_employer_rate"),
      nssf_tier1_limit: fieldValue("id_payroll_nssf_tier1_limit"),
      nssf_pensionable_cap: fieldValue("id_payroll_nssf_pensionable_cap"),
      shif_rate: fieldValue("id_payroll_shif_rate"),
      housing_levy_employee_rate: fieldValue("id_payroll_housing_levy_employee_rate"),
      housing_levy_employer_rate: fieldValue("id_payroll_housing_levy_employer_rate"),
      paye_personal_relief: fieldValue("id_payroll_paye_personal_relief"),
      paye_band_1_max: fieldValue("id_payroll_paye_band_1_max"),
      paye_band_1_rate: fieldValue("id_payroll_paye_band_1_rate"),
      paye_band_2_max: fieldValue("id_payroll_paye_band_2_max"),
      paye_band_2_rate: fieldValue("id_payroll_paye_band_2_rate"),
      paye_band_3_max: fieldValue("id_payroll_paye_band_3_max"),
      paye_band_3_rate: fieldValue("id_payroll_paye_band_3_rate"),
      paye_band_4_rate: fieldValue("id_payroll_paye_band_4_rate"),
      nita_levy_amount: fieldValue("id_payroll_nita_levy_amount"),
      wiba_insurance_amount: fieldValue("id_payroll_wiba_insurance_amount"),
    };
  }

  function setText(id, value) {
    const node = document.getElementById(id);
    if (node) node.textContent = formatMoney(value);
  }

  function setAmountCell(id, value) {
    const node = document.getElementById(id);
    if (!node) return;
    const amount = q(value);
    node.textContent = amount.toLocaleString("en-KE", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  }

  function fieldText(id) {
    const input = document.getElementById(id);
    return input ? String(input.value || "").trim() : "";
  }

  function formatIsoDate(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, "0");
    const day = String(date.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  }

  function formatDisplayDate(isoDate) {
    if (!isoDate) return "—";
    const date = new Date(`${isoDate}T00:00:00`);
    return date.toLocaleDateString("en-KE", {
      day: "numeric",
      month: "short",
      year: "numeric",
    });
  }

  function payPeriodEndForFrequency(startIso, frequency) {
    if (!startIso) return "";
    const start = new Date(`${startIso}T00:00:00`);
    if (Number.isNaN(start.getTime())) return "";

    if (frequency === "daily") {
      return startIso;
    }
    if (frequency === "weekly") {
      const end = new Date(start);
      end.setDate(end.getDate() + 6);
      return formatIsoDate(end);
    }
    if (frequency === "monthly") {
      const end = new Date(start.getFullYear(), start.getMonth() + 1, 0);
      return formatIsoDate(end);
    }
    if (frequency === "annually") {
      const end = new Date(start);
      end.setFullYear(end.getFullYear() + 1);
      end.setDate(end.getDate() - 1);
      return formatIsoDate(end);
    }
    return startIso;
  }

  function defaultStartForFrequency(frequency) {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    if (frequency === "monthly") {
      return formatIsoDate(new Date(today.getFullYear(), today.getMonth(), 1));
    }
    if (frequency === "weekly") {
      const start = new Date(today);
      const day = start.getDay();
      const diff = day === 0 ? 6 : day - 1;
      start.setDate(start.getDate() - diff);
      return formatIsoDate(start);
    }
    if (frequency === "annually") {
      return formatIsoDate(new Date(today.getFullYear(), 0, 1));
    }
    return formatIsoDate(today);
  }

  function initRegisterPayroll() {
    const form = document.getElementById("register-payroll-form");
    if (!form) return;

    const employeeSelect = document.getElementById("id_payroll_employee");
    const frequencySelect = document.getElementById("id_payroll_frequency");
    const periodStartInput = document.getElementById("id_payroll_period_start");
    const periodEndDisplay = document.getElementById("payroll-period-end-display");
    const submitButton = document.getElementById("register-payroll-submit");
    const noEmployeesHint = document.getElementById("payroll-no-employees-hint");
    const netPayEl = document.getElementById("payroll-net-pay");

    const employeeChoices = parseJsonDataset(form, "employeeChoices", []);
    const registeredPayrollMap = parseJsonDataset(form, "registeredPayrollMap", {});

    function periodKey() {
      const start = periodStartInput && periodStartInput.value;
      const frequency = frequencySelect && frequencySelect.value;
      const end = payPeriodEndForFrequency(start, frequency);
      return start && end && frequency ? `${start}|${end}|${frequency}` : "";
    }

    function updatePayPeriodPreview() {
      const start = fieldText("id_payroll_period_start");
      const frequency = fieldText("id_payroll_frequency") || "monthly";
      const end = payPeriodEndForFrequency(start, frequency);
      if (periodEndDisplay) {
        periodEndDisplay.textContent = end ? formatDisplayDate(end) : "—";
      }
      refreshEmployeeOptions();
    }

    function refreshEmployeeOptions() {
      if (!employeeSelect) return;
      const registered = new Set(
        (registeredPayrollMap[periodKey()] || []).map((id) => String(id))
      );
      const preferredEmployee =
        (form.dataset.selectedEmployee || "").trim() || employeeSelect.value;
      const available = employeeChoices.filter(
        (employee) => !registered.has(String(employee.id))
      );

      employeeSelect.innerHTML = "";
      const placeholder = document.createElement("option");
      placeholder.value = "";
      placeholder.textContent = available.length
        ? "Select an employee"
        : "No employees available for this pay period";
      employeeSelect.appendChild(placeholder);

      available.forEach((employee) => {
        const option = document.createElement("option");
        option.value = String(employee.id);
        option.textContent = employee.label;
        if (String(employee.id) === String(preferredEmployee)) option.selected = true;
        employeeSelect.appendChild(option);
      });

      const hasAvailable = available.length > 0;
      employeeSelect.disabled = !hasAvailable;
      if (submitButton) submitButton.disabled = !hasAvailable;
      if (noEmployeesHint) noEmployeesHint.hidden = hasAvailable;

      if (
        preferredEmployee &&
        available.some((employee) => String(employee.id) === String(preferredEmployee))
      ) {
        employeeSelect.value = String(preferredEmployee);
        const employee = employeeChoices.find(
          (entry) => String(entry.id) === String(preferredEmployee)
        );
        const basicInput = document.getElementById("id_payroll_basic_salary");
        if (employee && employee.salary && basicInput && !basicInput.value) {
          basicInput.value = employee.salary;
        }
      } else if (
        preferredEmployee &&
        !available.some((employee) => String(employee.id) === String(preferredEmployee))
      ) {
        employeeSelect.value = "";
      }
    }

    function applySelectedEmployee() {
      refreshEmployeeOptions();
      recalculatePayroll();
    }

    window.sheriaRefreshPayrollRegister = applySelectedEmployee;

    function recalculatePayroll() {
      const gross = sumEarnings();
      const settings = readRateSettings();
      const nssf = calculateNssf(
        gross,
        settings.nssf_employee_rate,
        settings.nssf_employer_rate,
        settings.nssf_tier1_limit,
        settings.nssf_pensionable_cap
      );
      const shif = calculatePercentage(gross, settings.shif_rate);
      const housingEmployee = calculatePercentage(gross, settings.housing_levy_employee_rate);
      const housingEmployer = calculatePercentage(gross, settings.housing_levy_employer_rate);
      const taxableIncome = q(gross - nssf.employeeAmount);
      const paye = calculatePaye(taxableIncome, settings);
      const totalDeductions = q(nssf.employeeAmount + shif + housingEmployee + paye);
      const netPay = q(gross - totalDeductions);
      const employerCost = q(
        nssf.employerAmount +
          housingEmployer +
          settings.nita_levy_amount +
          settings.wiba_insurance_amount
      );

      setText("payroll-gross-earnings", gross);
      setAmountCell("calc-nssf-employee", nssf.employeeAmount);
      setAmountCell("calc-shif", shif);
      setAmountCell("calc-housing-employee", housingEmployee);
      setAmountCell("calc-taxable-income", taxableIncome);
      setAmountCell("calc-paye", paye);
      setAmountCell("calc-nssf-employer", nssf.employerAmount);
      setAmountCell("calc-housing-employer", housingEmployer);
      setAmountCell("calc-nita", settings.nita_levy_amount);
      setAmountCell("calc-wiba", settings.wiba_insurance_amount);
      setText("payroll-total-deductions", totalDeductions);
      setAmountCell("payroll-total-deductions-inline", totalDeductions);
      setText("payroll-net-pay", netPay);
      setText("payroll-employer-cost", employerCost);
      setAmountCell("payroll-employer-cost-inline", employerCost);
      if (netPayEl) netPayEl.classList.toggle("is-negative", netPay < 0);
    }

    if (employeeSelect) {
      employeeSelect.addEventListener("change", () => {
        form.dataset.selectedEmployee = employeeSelect.value || "";
        const employee = employeeChoices.find(
          (entry) => String(entry.id) === employeeSelect.value
        );
        const basicInput = document.getElementById("id_payroll_basic_salary");
        if (employee && employee.salary && basicInput && !basicInput.value) {
          basicInput.value = employee.salary;
          recalculatePayroll();
        }
      });
    }

    if (frequencySelect) {
      frequencySelect.addEventListener("change", () => {
        if (periodStartInput && !periodStartInput.dataset.userEdited) {
          periodStartInput.value = defaultStartForFrequency(frequencySelect.value);
        }
        updatePayPeriodPreview();
        recalculatePayroll();
      });
    }

    if (periodStartInput) {
      periodStartInput.addEventListener("input", () => {
        periodStartInput.dataset.userEdited = "1";
        updatePayPeriodPreview();
      });
      periodStartInput.addEventListener("change", updatePayPeriodPreview);
    }

    [periodStartInput, frequencySelect].forEach((input) => {
      if (!input) return;
      input.addEventListener("change", recalculatePayroll);
    });

    form.querySelectorAll("input, select, textarea").forEach((input) => {
      if (input === periodStartInput || input === frequencySelect) return;
      input.addEventListener("input", recalculatePayroll);
      input.addEventListener("change", recalculatePayroll);
    });

    refreshEmployeeOptions();
    updatePayPeriodPreview();
    recalculatePayroll();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initRegisterPayroll);
  } else {
    initRegisterPayroll();
  }
})();
