document.addEventListener("DOMContentLoaded", function () {
  "use strict";

  var page = document.getElementById("payroll-page");
  if (!page) return;

  function navigateRow(row) {
    var href = row && row.dataset.href;
    if (href) window.location.href = href;
  }

  page.addEventListener("click", function (event) {
    var row = event.target.closest("tr.is-clickable-row");
    if (!row || !page.contains(row)) return;
    if (event.target.closest("a, button, input, label, select, textarea")) return;
    navigateRow(row);
  });

  page.addEventListener("keydown", function (event) {
    if (event.key !== "Enter" && event.key !== " ") return;
    var row = event.target.closest("tr.is-clickable-row");
    if (!row || !page.contains(row)) return;
    event.preventDefault();
    navigateRow(row);
  });
});
