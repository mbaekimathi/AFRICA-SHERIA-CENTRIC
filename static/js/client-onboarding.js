document.addEventListener("DOMContentLoaded", () => {
  window.initPhoneCountryPicker?.();

  const forceUppercase = (root = document) => {
    root.querySelectorAll("input, textarea").forEach((input) => {
      if (
        input.type === "email" ||
        input.type === "file" ||
        input.type === "hidden" ||
        input.type === "radio" ||
        input.type === "checkbox" ||
        input.type === "search" ||
        input.id === "id_client_email" ||
        input.id === "id_onboard_email"
      ) {
        return;
      }
      input.classList.add("input-uppercase");
      const forceUpper = () => {
        const start = input.selectionStart;
        const end = input.selectionEnd;
        const upper = input.value.toUpperCase();
        if (input.value !== upper) {
          input.value = upper;
          if (typeof start === "number" && typeof end === "number") {
            input.setSelectionRange(start, end);
          }
        }
      };
      input.addEventListener("input", forceUpper);
      forceUpper();
    });
  };
  forceUppercase();

  const typeSelect = document.getElementById("id_onboard_client_type");
  const individualNames = document.getElementById("individual-name-fields");
  const corporateNames = document.getElementById("corporate-name-fields");
  const corporateNameLabel = document.getElementById("corporate-name-label");
  const individualId = document.getElementById("individual-id-fields");
  const corporateReg = document.getElementById("corporate-reg-fields");
  const citizenField = document.getElementById("citizen-id-field");
  const alienField = document.getElementById("alien-id-field");

  const syncCorporateKind = () => {
    const kind = document.querySelector(
      'input[name="corporate_kind"]:checked'
    )?.value;
    const isCompany = kind === "company";
    if (corporateNameLabel) {
      corporateNameLabel.textContent = isCompany
        ? "Company name"
        : "Business name";
    }
  };

  const syncType = () => {
    const isCorporate = typeSelect?.value === "corporate";
    individualNames?.classList.toggle("is-hidden", isCorporate);
    corporateNames?.classList.toggle("is-hidden", !isCorporate);
    individualId?.classList.toggle("is-hidden", isCorporate);
    corporateReg?.classList.toggle("is-hidden", !isCorporate);
    if (isCorporate) {
      const checked = document.querySelector(
        'input[name="corporate_kind"]:checked'
      );
      if (!checked) {
        const first = document.querySelector('input[name="corporate_kind"]');
        if (first) first.checked = true;
      }
      syncCorporateKind();
    }
  };

  const syncIdType = () => {
    const selected = document.querySelector(
      'input[name="id_type"]:checked'
    )?.value;
    const isAlien = selected === "non_citizen";
    citizenField?.classList.toggle("is-hidden", isAlien);
    alienField?.classList.toggle("is-hidden", !isAlien);
  };

  typeSelect?.addEventListener("change", syncType);
  document.querySelectorAll('input[name="id_type"]').forEach((input) => {
    input.addEventListener("change", syncIdType);
  });
  document.querySelectorAll('input[name="corporate_kind"]').forEach((input) => {
    input.addEventListener("change", syncCorporateKind);
  });

  syncType();
  syncIdType();
  syncCorporateKind();
});
