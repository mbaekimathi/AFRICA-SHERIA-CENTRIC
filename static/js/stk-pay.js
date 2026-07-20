(function () {
  function lockForm(form) {
    var btn = form.querySelector('button[type="submit"]');
    if (!btn || btn.classList.contains("is-loading")) {
      return false;
    }

    var loadingText =
      btn.getAttribute("data-loading-text") || "Please wait…";

    btn.classList.add("is-loading");
    btn.disabled = true;
    btn.setAttribute("aria-busy", "true");
    btn.innerHTML =
      '<span class="btn-spinner" aria-hidden="true"></span>' +
      "<span>" +
      loadingText +
      "</span>";

    // Do not disable text/number inputs — disabled fields are omitted from POST.
    form.classList.add("is-submitting");
    form.setAttribute("aria-busy", "true");

    return true;
  }

  document.querySelectorAll("form[data-stk-loading]").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      if (!lockForm(form)) {
        event.preventDefault();
      }
    });
  });
})();
