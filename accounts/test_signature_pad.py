import base64
import shutil
import tempfile
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image, ImageDraw

from accounts.models import (
    CompanyDigitalSignatureSetting,
    Employee,
    EmployeeDigitalSignatureSetting,
    FirmCompanyInformation,
)


def signature_data_url(*, blank=False):
    """A transparent PNG with a pen stroke, as the sketch pad sends it."""
    image = Image.new("RGBA", (400, 160), (0, 0, 0, 0))
    if not blank:
        draw = ImageDraw.Draw(image)
        draw.line([(40, 120), (120, 40), (200, 120), (300, 50)], fill=(16, 24, 40, 255), width=4)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode()
    return f"data:image/png;base64,{encoded}"


def signature_upload(name="signed-sheet.png"):
    image = Image.new("RGB", (300, 120), "white")
    draw = ImageDraw.Draw(image)
    draw.line([(30, 90), (140, 30), (260, 90)], fill=(20, 20, 20), width=5)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


class SignaturePadTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls._media_root = tempfile.mkdtemp(prefix="signature-test-media-")
        cls._media_override = override_settings(MEDIA_ROOT=cls._media_root)
        cls._media_override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._media_override.disable()
        shutil.rmtree(cls._media_root, ignore_errors=True)

    def setUp(self):
        self.user = Employee.objects.create_user(
            login_code="888888",
            password="test-pass-123",
            first_name="Sign",
            last_name="Partner",
            personal_email="sign.partner@example.com",
            role=Employee.Role.MANAGING_PARTNER,
            status=Employee.Status.ACTIVE,
        )
        self.client.force_login(self.user)
        self.stamp_url = self.user.workspace_url(
            "dashboard",
            "system-settings",
            "document-settings",
            "digital-stamp",
        )
        self.signature_url = self.user.workspace_url(
            "dashboard",
            "system-settings",
            "document-settings",
            "default-signature",
        )
        FirmCompanyInformation.get_solo()
        self.stamp_payload = {
            "template": "classic",
            "accent": "ink",
            "show_firm_name": "on",
            "show_status": "on",
            "show_approver": "on",
            "show_date": "on",
        }
        self.signature_payload = {
            "template": "classic",
            "accent": "navy",
            "default_title": "Authorized Signatory",
            "show_firm_name": "on",
            "show_name": "on",
            "show_title": "on",
            "show_date": "on",
        }

    def test_stamp_page_offers_the_signature_pad(self):
        response = self.client.get(self.stamp_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sketch your signature")
        self.assertContains(response, "Your signature will show here")
        self.assertContains(response, "data-signature-canvas")
        self.assertContains(response, 'name="signature_drawing"')

    def test_signature_page_offers_the_signature_pad(self):
        response = self.client.get(self.signature_url)
        self.assertContains(response, "data-signature-canvas")
        self.assertContains(response, 'enctype="multipart/form-data"')

    def test_sketching_from_the_stamp_page_saves_the_signature(self):
        response = self.client.post(
            self.stamp_url,
            {**self.stamp_payload, "signature_drawing": signature_data_url()},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        setting = CompanyDigitalSignatureSetting.get_solo()
        self.assertTrue(setting.has_drawing)
        self.assertEqual(setting.updated_by, self.user)
        # Documents render the sketch instead of the designed block.
        self.assertContains(response, "doc-signature--drawn")
        self.assertContains(response, setting.signature_image.url)

    def test_sketching_from_the_signature_page_saves_the_signature(self):
        response = self.client.post(
            self.signature_url,
            {
                **self.signature_payload,
                "signature_drawing": signature_data_url(),
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(CompanyDigitalSignatureSetting.get_solo().has_drawing)
        self.assertContains(response, "doc-signature--drawn")

    def test_saved_sketch_is_trimmed_to_the_ink(self):
        self.client.post(
            self.stamp_url,
            {**self.stamp_payload, "signature_drawing": signature_data_url()},
        )
        setting = CompanyDigitalSignatureSetting.get_solo()
        with Image.open(setting.signature_image.path) as saved:
            self.assertLess(saved.width, 400)
            self.assertEqual(saved.mode, "RGBA")

    def test_uploading_a_signature_sheet_is_accepted(self):
        response = self.client.post(
            self.stamp_url,
            {**self.stamp_payload, "signature_image": signature_upload()},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(CompanyDigitalSignatureSetting.get_solo().has_drawing)

    def test_clearing_restores_the_designed_signature_block(self):
        self.client.post(
            self.stamp_url,
            {**self.stamp_payload, "signature_drawing": signature_data_url()},
        )
        response = self.client.post(
            self.signature_url,
            {**self.signature_payload, "clear_signature_image": "on"},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(CompanyDigitalSignatureSetting.get_solo().has_drawing)
        self.assertNotContains(response, "doc-signature--drawn")
        # Without an uploaded mark, the signatory name is the signature.
        self.assertContains(response, "doc-signature--named")
        self.assertContains(response, "Sign Partner")

    def test_without_an_upload_the_preview_shows_the_signatory_name(self):
        response = self.client.get(self.signature_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "doc-signature--named")
        self.assertContains(response, "Sign Partner")
        self.assertNotContains(response, "doc-signature--drawn")

    def test_the_title_line_shows_the_signatory_role(self):
        response = self.client.get(self.signature_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Managing Partner")
        self.assertNotContains(
            response, '<span class="doc-signature__title">Authorized Signatory</span>'
        )

    def test_an_invoice_signature_carries_the_signer_role(self):
        from accounts.digital_signature import signature_render_context

        ctx = signature_render_context(
            name=self.user.get_full_name(),
            signer=self.user,
            date_display="01 Jan 2026",
        )
        self.assertEqual(ctx["signature_title"], "Managing Partner")

    def test_the_fallback_title_covers_signatories_without_a_role(self):
        from accounts.digital_signature import signature_render_context

        ctx = signature_render_context(name="Firm", date_display="01 Jan 2026")
        self.assertEqual(ctx["signature_title"], "Authorized Signatory")

    def test_blank_pad_leaves_the_signature_untouched(self):
        response = self.client.post(
            self.stamp_url,
            {
                **self.stamp_payload,
                "signature_drawing": signature_data_url(blank=True),
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(CompanyDigitalSignatureSetting.get_solo().has_drawing)

    def test_a_broken_drawing_payload_is_rejected(self):
        response = self.client.post(
            self.stamp_url,
            {**self.stamp_payload, "signature_drawing": "not-a-data-url"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(CompanyDigitalSignatureSetting.get_solo().has_drawing)
        self.assertContains(response, "Clear the pad and sign again")


class MyDigitalSignatureTests(TestCase):
    """My digital signature overrides the firm default for that signatory."""

    @classmethod
    def setUpClass(cls):
        cls._media_root = tempfile.mkdtemp(prefix="my-signature-test-media-")
        cls._media_override = override_settings(MEDIA_ROOT=cls._media_root)
        cls._media_override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._media_override.disable()
        shutil.rmtree(cls._media_root, ignore_errors=True)

    def setUp(self):
        self.user = Employee.objects.create_user(
            login_code="777777",
            password="test-pass-123",
            first_name="Own",
            last_name="Hand",
            personal_email="own.hand@example.com",
            role=Employee.Role.ADVOCATE,
            status=Employee.Status.ACTIVE,
        )
        self.other = Employee.objects.create_user(
            login_code="666666",
            password="test-pass-123",
            first_name="Other",
            last_name="Advocate",
            personal_email="other.advocate@example.com",
            role=Employee.Role.ADVOCATE,
            status=Employee.Status.ACTIVE,
        )
        self.client.force_login(self.user)
        self.url = self.user.workspace_url(
            "dashboard", "my-tools", "my-digital-signature"
        )
        FirmCompanyInformation.get_solo()
        self.company = CompanyDigitalSignatureSetting.get_solo()
        self.company.template = CompanyDigitalSignatureSetting.Template.FORMAL
        self.company.save()
        self.payload = {
            "template": "script",
            "accent": "teal",
            "default_title": "Authorized Signatory",
            "show_firm_name": "on",
            "show_name": "on",
            "show_title": "on",
            "show_date": "on",
        }

    def personal(self):
        return EmployeeDigitalSignatureSetting.objects.filter(
            employee=self.user
        ).first()

    def test_page_starts_on_the_firm_default(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "currently carry the firm default")
        self.assertIsNone(self.personal())

    def test_saving_creates_a_personal_signature(self):
        response = self.client.post(self.url, self.payload, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "overrides the firm default")
        self.assertContains(response, "Use the firm default instead")
        setting = self.personal()
        self.assertIsNotNone(setting)
        self.assertEqual(
            setting.template, EmployeeDigitalSignatureSetting.Template.SCRIPT
        )
        # The firm default is left untouched for everyone else.
        self.company.refresh_from_db()
        self.assertEqual(
            self.company.template,
            CompanyDigitalSignatureSetting.Template.FORMAL,
        )

    def test_a_saved_signature_signs_that_employees_documents(self):
        from accounts.digital_signature import signature_render_context

        self.client.post(
            self.url,
            {**self.payload, "signature_drawing": signature_data_url()},
        )
        ctx = signature_render_context(
            name=self.user.get_full_name(), signer=self.user
        )
        self.assertEqual(ctx["digital_signature"], self.personal())
        self.assertTrue(ctx["digital_signature"].has_drawing)

    def test_other_signatories_keep_the_firm_default(self):
        from accounts.digital_signature import signature_render_context

        self.client.post(self.url, self.payload)
        ctx = signature_render_context(
            name=self.other.get_full_name(), signer=self.other
        )
        self.assertEqual(
            ctx["digital_signature"].pk, CompanyDigitalSignatureSetting.get_solo().pk
        )
        self.assertIsInstance(
            ctx["digital_signature"], CompanyDigitalSignatureSetting
        )

    def test_reverting_hands_the_employee_back_to_the_firm_default(self):
        self.client.post(
            self.url,
            {**self.payload, "signature_drawing": signature_data_url()},
        )
        response = self.client.post(
            self.url, {"use_company_signature": "1"}, follow=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self.personal())
        self.assertContains(response, "firm default signature again")

    def test_the_firm_default_page_still_edits_the_company_row(self):
        firm_url = self.user.workspace_url(
            "dashboard",
            "system-settings",
            "document-settings",
            "default-signature",
        )
        self.client.post(firm_url, {**self.payload, "template": "stacked"})
        self.company.refresh_from_db()
        self.assertEqual(
            self.company.template,
            CompanyDigitalSignatureSetting.Template.STACKED,
        )
        self.assertIsNone(self.personal())
