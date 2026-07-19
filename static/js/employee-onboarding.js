document.addEventListener("DOMContentLoaded", () => {
  const mobileFields = document.getElementById("mobile-payment-fields");
  const bankFields = document.getElementById("bank-payment-fields");

  const syncPaymentMethod = () => {
    const method = document.querySelector(
      'input[name="payment_method"]:checked'
    )?.value;
    const isMobile = method === "mobile";
    const isBank = method === "bank";
    mobileFields?.classList.toggle("is-hidden", !isMobile);
    bankFields?.classList.toggle("is-hidden", !isBank);
  };

  document
    .querySelectorAll('input[name="payment_method"]')
    .forEach((input) => input.addEventListener("change", syncPaymentMethod));

  if (!document.querySelector('input[name="payment_method"]:checked')) {
    const first = document.querySelector('input[name="payment_method"]');
    if (first) first.checked = true;
  }
  syncPaymentMethod();

  document.querySelectorAll("#employee-onboarding-form input").forEach((input) => {
    if (
      input.type === "file" ||
      input.type === "radio" ||
      input.type === "hidden" ||
      input.id === "id_mobile_money_number" ||
      input.id === "id_bank_account_number"
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
});
