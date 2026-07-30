from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import (
    Client,
    Document,
    Employee,
    GoogleDriveConnection,
    LitigationCase,
)

VIEWS = "accounts.views"


class StartFromTemplateCaseTests(TestCase):
    def setUp(self):
        self.user = Employee.objects.create_user(
            login_code="556677",
            password="test-pass-123",
            first_name="Docs",
            last_name="Partner",
            personal_email="docs.partner@example.com",
            role=Employee.Role.MANAGING_PARTNER,
            status=Employee.Status.ACTIVE,
        )
        self.client.force_login(self.user)
        client_person = Client.objects.create(
            email="matter.client@example.com",
            first_name="Matter",
            last_name="Client",
            status=Client.Status.ACTIVE,
        )
        self.case = LitigationCase.objects.create(
            filing_date=timezone.localdate(),
            client=client_person,
            court_rank="high_court",
            case_category="civil",
            case_type="suit",
            station="nairobi",
            status=LitigationCase.Status.ACTIVE,
            assigned_to=self.user,
        )
        connection = GoogleDriveConnection.get_solo()
        connection.account_email = "firm@example.com"
        connection.access_token = "test-access-token"
        connection.refresh_token = "test-refresh-token"
        connection.root_folder_id = "root-id"
        connection.templates_forms_folder_id = "templates-id"
        connection.templates_forms_category_folder_ids = {
            "notices": "notices-id",
        }
        connection.save()

        self.url = reverse(
            "accounts:upload_case_documents",
            kwargs={
                "role": self.user.role_slug,
                "case_id": self.case.pk,
            },
        )
        self.template_id = "template-master-id"
        self.copy_id = "case-working-copy-id"

        library_patcher = patch(
            f"{VIEWS}._templates_library_payload",
            return_value={
                "connected": True,
                "categories": [
                    {"slug": "notices", "label": "Notices", "count": 1}
                ],
                "files": [
                    {
                        "id": self.template_id,
                        "name": "Notice to vacate",
                        "category": "notices",
                        "category_label": "Notices",
                        "mime_type": "application/vnd.google-apps.document",
                    }
                ],
                "choices": [
                    (self.template_id, "Notices — Notice to vacate"),
                ],
                "settings_url": "",
            },
        )
        library_patcher.start()
        self.addCleanup(library_patcher.stop)

    def _payload(self, **overrides):
        payload = {
            "document_action": "start_from_template",
            "template-category": "notices",
            "template-template_file_id": self.template_id,
            "template-title": "Notice for this case",
            "template-party_type": "plaintiff",
            "template-notes": "",
        }
        payload.update(overrides)
        return payload

    def test_use_template_copies_master_and_opens_working_copy(self):
        with (
            patch(
                f"{VIEWS}._assert_template_in_category",
                return_value={
                    "id": self.template_id,
                    "name": "Notice to vacate",
                    "mimeType": "application/vnd.google-apps.document",
                    "parents": ["notices-id"],
                },
            ),
            patch(
                f"{VIEWS}.ensure_case_drive_folder",
                return_value="case-folder-id",
            ),
            patch(
                f"{VIEWS}.copy_drive_file",
                return_value={
                    "id": self.copy_id,
                    "name": "Notice for this case",
                    "mimeType": "application/vnd.google-apps.document",
                    "webViewLink": (
                        f"https://docs.google.com/document/d/{self.copy_id}/edit"
                    ),
                },
            ) as copy_mock,
        ):
            response = self.client.post(self.url, self._payload())

        copy_mock.assert_called_once_with(
            self.template_id,
            name="Notice for this case",
            parent_id="case-folder-id",
        )
        document = Document.objects.get(case=self.case, title="Notice for this case")
        self.assertEqual(document.drive_file_id, self.copy_id)
        self.assertNotEqual(document.drive_file_id, self.template_id)
        self.assertEqual(document.source, Document.Source.GOOGLE_DOC)
        self.assertIn("Started from Notices template", document.description)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            reverse(
                "accounts:open_document",
                kwargs={
                    "role": self.user.role_slug,
                    "document_id": document.pk,
                },
            ),
        )

    def test_open_working_copy_uses_copy_drive_id_not_template(self):
        document = Document.objects.create(
            case=self.case,
            title="Notice for this case",
            source=Document.Source.GOOGLE_DOC,
            drive_file_id=self.copy_id,
            mime_type="application/vnd.google-apps.document",
            description="Started from Notices template.",
            uploaded_by=self.user,
            party_type="plaintiff",
        )
        self.assertIn(self.copy_id, document.open_url)
        self.assertNotIn(self.template_id, document.open_url)
