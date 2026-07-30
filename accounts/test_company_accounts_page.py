from decimal import Decimal

from django.test import TestCase

from accounts.models import CompanyExpenseAccount, Employee


class CompanyAccountsPageTests(TestCase):
    def setUp(self):
        self.user = Employee.objects.create_user(
            login_code="565656",
            password="test-pass-123",
            first_name="Finance",
            last_name="Partner",
            personal_email="finance.partner@example.com",
            role=Employee.Role.MANAGING_PARTNER,
            status=Employee.Status.ACTIVE,
        )
        self.client.force_login(self.user)
        self.url = self.user.workspace_url(
            "dashboard",
            "finance-billing",
            "company-accounts",
        )
        self.account = CompanyExpenseAccount.objects.create(
            name="TRAVEL",
            bank_name="KCB",
            bank_account_number="12345",
            description="Travel costs",
            payment_methods=[
                CompanyExpenseAccount.PaymentMethod.CASH,
            ],
            balance=Decimal("0.00"),
            created_by=self.user,
        )

    def test_page_offers_edit_and_delete_for_created_account(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "js-edit-company-account")
        self.assertContains(response, "delete-company-account")
        self.assertContains(response, 'data-account-id="{}"'.format(self.account.pk))

    def test_user_can_edit_any_account_including_a_default(self):
        default_account = CompanyExpenseAccount.get_main_client_accounts()

        response = self.client.post(
            self.url,
            {
                "action": "edit-company-account",
                "account_id": default_account.pk,
                "edit-name": "CLIENT FUNDS",
                "edit-bank_name": "EQUITY BANK",
                "edit-bank_account_number": "998877",
                "edit-description": "Updated default account",
                "edit-payment_methods": [
                    CompanyExpenseAccount.PaymentMethod.BANK_TRANSFER,
                    CompanyExpenseAccount.PaymentMethod.MPESA,
                ],
            },
        )

        self.assertRedirects(response, self.url)
        default_account.refresh_from_db()
        self.assertEqual(default_account.name, "CLIENT FUNDS")
        self.assertEqual(default_account.bank_name, "EQUITY BANK")
        self.assertEqual(
            default_account.payment_methods,
            ["bank_transfer", "mpesa"],
        )
        self.assertEqual(
            default_account.system_key,
            CompanyExpenseAccount.SYSTEM_MAIN_CLIENT_ACCOUNTS,
        )

    def test_user_can_delete_created_account(self):
        response = self.client.post(
            self.url,
            {
                "action": "delete-company-account",
                "account_id": self.account.pk,
            },
        )

        self.assertRedirects(response, self.url)
        self.assertFalse(
            CompanyExpenseAccount.objects.filter(pk=self.account.pk).exists()
        )

    def test_default_account_cannot_be_deleted(self):
        default_account = CompanyExpenseAccount.get_petty_cash_book()

        response = self.client.post(
            self.url,
            {
                "action": "delete-company-account",
                "account_id": default_account.pk,
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            CompanyExpenseAccount.objects.filter(pk=default_account.pk).exists()
        )
        self.assertContains(response, "Default company accounts cannot be deleted.")
