document.addEventListener("DOMContentLoaded", function () {
  "use strict";

  var page = document.getElementById("payroll-page");
  if (!page) return;

  var registerModal = document.getElementById("register-payroll-modal");
  var registerSubtitle = document.getElementById("register-payroll-modal-subtitle");
  var registerCancel = document.getElementById("register-payroll-modal-cancel");

  function selectRegisterEmployee(employeeId) {
    var form = document.getElementById("register-payroll-form");
    if (!form) return;
    if (employeeId) {
      form.dataset.selectedEmployee = String(employeeId);
    } else {
      delete form.dataset.selectedEmployee;
    }
    if (typeof window.sheriaRefreshPayrollRegister === "function") {
      window.sheriaRefreshPayrollRegister();
    }
  }

  function openRegisterModal(employeeId, employeeName) {
    if (!registerModal || typeof registerModal.showModal !== "function") return;
    selectRegisterEmployee(employeeId || "");
    if (registerSubtitle) {
      registerSubtitle.textContent = employeeName
        ? "Register payroll for " + employeeName + "."
        : "Register earnings, statutory deductions, and employer costs.";
    }
    registerModal.showModal();
  }

  function closeRegisterModal() {
    if (registerModal && typeof registerModal.close === "function") {
      registerModal.close();
    }
  }

  page.querySelectorAll(".js-open-register-payroll").forEach(function (btn) {
    btn.addEventListener("click", function (event) {
      event.preventDefault();
      event.stopPropagation();
      var employeeId = btn.getAttribute("data-register-employee") || "";
      var nameNode = btn.closest("tr") && btn.closest("tr").querySelector(".person-cell__name");
      var employeeName = nameNode ? nameNode.textContent.trim() : "";
      openRegisterModal(employeeId, employeeName);
    });
  });

  if (registerCancel) {
    registerCancel.addEventListener("click", closeRegisterModal);
  }

  if (registerModal) {
    registerModal.addEventListener("click", function (event) {
      if (event.target === registerModal) closeRegisterModal();
    });
  }

  function navigateRow(row) {
    var registerEmployee = row && row.getAttribute("data-register-employee");
    if (registerEmployee) {
      var nameNode = row.querySelector(".person-cell__name");
      openRegisterModal(registerEmployee, nameNode ? nameNode.textContent.trim() : "");
      return;
    }
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

  if (page.getAttribute("data-open-register") === "1") {
    openRegisterModal(
      page.getAttribute("data-register-employee") || "",
      ""
    );
  }
});
