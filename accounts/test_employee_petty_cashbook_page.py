from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from accounts.models import (
    CompanyExpensePayment,
    Employee,
    PettyCashExpenseRequest,
)


class EmployeePettyCashbookSidebarTests(TestCase):
    def setUp(self):
        self.user = Employee.objects.create_user(
            login_code="556677",
            password="test-pass-123",
            first_name="Petty",
            last_name="Partner",
            personal_email="petty.partner@example.com",
            role=Employee.Role.MANAGING_PARTNER,
            status=Employee.Status.ACTIVE,
        )
        self.client.force_login(self.user)
        self.url = self.user.workspace_url(
            "dashboard",
            "finance-billing",
            "employee-accounts",
            "employee-petty-cashbook",
        )

    def test_sidebar_register_expense_opens_modal(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response, "accounts/employee_petty_cashbook.html"
        )
        nav_slugs = [
            item["slug"] for item in response.context["page_nav_items"]
        ]
        self.assertIn("register-petty-cash-expense", nav_slugs)
        self.assertContains(response, 'href="#register-petty-cash-expense"')
        self.assertContains(
            response, 'a[href="#register-petty-cash-expense"]'
        )
        self.assertContains(response, "register-petty-cash-expense-modal")
        self.assertContains(response, 'enctype="multipart/form-data"')
        self.assertContains(response, "Payment attachment")
        self.assertContains(response, "id_petty_cash_payment_attachment")

    def test_register_expense_without_attachment(self):
        response = self.client.post(
            self.url,
            {
                "action": "register-petty-cash-expense",
                "expense_type": CompanyExpensePayment.ExpenseType.OTHER,
                "amount": "250.00",
                "description": "Office supplies from town",
            },
        )
        self.assertEqual(response.status_code, 302)
        expense = PettyCashExpenseRequest.objects.get(employee=self.user)
        self.assertEqual(expense.amount, 250)
        self.assertFalse(bool(expense.payment_attachment))

        dashboard_response = self.client.get(
            self.user.workspace_url("dashboard")
        )
        finance_item = next(
            item
            for item in dashboard_response.context["page_nav_items"]
            if item["slug"] == "finance-billing"
        )
        self.assertEqual(finance_item["badge_count"], 1)
        self.assertContains(
            dashboard_response,
            'data-page-badge="finance-billing"',
        )

    def test_register_expense_with_payment_attachment(self):
        upload = SimpleUploadedFile(
            "receipt.png",
            b"\x89PNG\r\n\x1a\n" + b"\x00" * 32,
            content_type="image/png",
        )
        response = self.client.post(
            self.url,
            {
                "action": "register-petty-cash-expense",
                "expense_type": CompanyExpensePayment.ExpenseType.OTHER,
                "amount": "480.50",
                "description": "Courier payment with receipt",
                "payment_attachment": upload,
            },
        )
        self.assertEqual(response.status_code, 302)
        expense = PettyCashExpenseRequest.objects.get(employee=self.user)
        self.assertTrue(expense.payment_attachment)
        self.assertIn("receipt", expense.payment_attachment.name)
