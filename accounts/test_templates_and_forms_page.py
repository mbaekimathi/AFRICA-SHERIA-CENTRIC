from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from accounts.google_drive import GoogleDriveAPIError
from accounts.models import Employee, GoogleDriveConnection

VIEWS = "accounts.views"


class TemplatesAndFormsPostTests(TestCase):
    def setUp(self):
        self.user = Employee.objects.create_user(
            login_code="555555",
            password="test-pass-123",
            first_name="Template",
            last_name="Partner",
            personal_email="template.partner@example.com",
            role=Employee.Role.MANAGING_PARTNER,
            status=Employee.Status.ACTIVE,
        )
        self.client.force_login(self.user)
        self.url = self.user.workspace_url(
            "dashboard",
            "system-settings",
            "document-settings",
            "templates-and-forms",
        )
        connection = GoogleDriveConnection.get_solo()
        connection.account_email = "firm@example.com"
        connection.access_token = "test-access-token"
        connection.refresh_token = "test-refresh-token"
        connection.root_folder_id = "root-id"
        connection.templates_forms_folder_id = "templates-id"
        connection.templates_forms_category_folder_ids = {"letters": "letters-id"}
        connection.save()
        self.connection = connection

        patcher = patch(
            f"{VIEWS}.ensure_templates_forms_folder", return_value=connection
        )
        patcher.start()
        self.addCleanup(patcher.stop)

        library_patcher = patch(
            f"{VIEWS}.list_templates_forms_library",
            return_value=[
                {
                    "slug": "letters",
                    "label": "Letters",
                    "folder_id": "letters-id",
                    "folder_url": "https://drive.google.com/drive/folders/letters-id",
                    "files": [
                        {
                            "id": "company-letter-id",
                            "name": "Company demand letter",
                            "mime_type": "application/vnd.google-apps.document",
                            "open_url": "https://docs.google.com/document/d/company-letter-id/edit",
                            "category": "letters",
                            "category_label": "Letters",
                        }
                    ],
                    "count": 1,
                }
            ],
        )
        library_patcher.start()
        self.addCleanup(library_patcher.stop)

        folder_patcher = patch(
            f"{VIEWS}.templates_forms_category_folder_id", return_value="letters-id"
        )
        folder_patcher.start()
        self.addCleanup(folder_patcher.stop)

        cache_patcher = patch(f"{VIEWS}.invalidate_templates_forms_library_cache")
        cache_patcher.start()
        self.addCleanup(cache_patcher.stop)

        mine_ensure = patch(
            f"{VIEWS}.ensure_employee_templates_folder", return_value=self.user
        )
        mine_ensure.start()
        self.addCleanup(mine_ensure.stop)

        mine_list = patch(
            f"{VIEWS}.list_employee_templates_library",
            return_value=[
                {
                    "slug": "letters",
                    "label": "Letters",
                    "folder_id": "my-letters-id",
                    "folder_url": "https://drive.google.com/drive/folders/my-letters-id",
                    "files": [
                        {
                            "id": "my-letter-id",
                            "name": "My demand letter",
                            "mime_type": "application/vnd.google-apps.document",
                            "open_url": "https://docs.google.com/document/d/my-letter-id/edit",
                            "category": "letters",
                            "category_label": "Letters",
                            "scope": "mine",
                            "can_manage": True,
                        }
                    ],
                    "count": 1,
                }
            ],
        )
        mine_list.start()
        self.addCleanup(mine_list.stop)

        mine_folder = patch(
            f"{VIEWS}.employee_template_category_folder_id",
            return_value="my-letters-id",
        )
        mine_folder.start()
        self.addCleanup(mine_folder.stop)

        mine_cache = patch(f"{VIEWS}.invalidate_employee_templates_library_cache")
        mine_cache.start()
        self.addCleanup(mine_cache.stop)

    def upload_payload(self, **overrides):
        payload = {
            "template_action": "upload",
            "scope": "company",
            "category": "letters",
            "title": "Engagement letter",
            "file": SimpleUploadedFile(
                "engagement.txt", b"letter body", content_type="text/plain"
            ),
        }
        payload.update(overrides)
        return payload

    def test_page_shows_company_and_my_templates_scope(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Company templates")
        self.assertContains(response, "My templates")
        self.assertContains(response, "data-templates-scope")
        self.assertContains(response, "Company demand letter")
        self.assertContains(response, "Duplicate")

    def test_library_groups_templates_by_document_type_then_category(self):
        with patch(
            f"{VIEWS}.list_templates_forms_library",
            return_value=[
                {
                    "slug": "letters",
                    "label": "Letters",
                    "folder_id": "letters-id",
                    "folder_url": "https://drive.google.com/drive/folders/letters-id",
                    "files": [
                        {
                            "id": "office-letter-id",
                            "name": "Engagement letter",
                            "category": "letters",
                            "category_label": "Letters",
                            "document_kind": "office",
                            "document_kind_label": "Office document",
                        },
                        {
                            "id": "court-letter-id",
                            "name": "Demand before action",
                            "category": "letters",
                            "category_label": "Letters",
                            "document_kind": "court",
                            "document_kind_label": "Court document",
                        },
                    ],
                    "count": 2,
                }
            ],
        ):
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        groups = response.context["templates_forms_groups"]
        self.assertEqual([group["kind"] for group in groups], ["court", "office"])
        self.assertEqual(
            [bucket["label"] for group in groups for bucket in group["categories"]],
            ["Letters", "Letters"],
        )
        self.assertEqual(
            [
                item["name"]
                for group in groups
                for bucket in group["categories"]
                for item in bucket["files"]
            ],
            ["Demand before action", "Engagement letter"],
        )
        self.assertContains(response, "template-subgroup__title")

    def test_my_templates_scope_lists_personal_files_with_manage_actions(self):
        response = self.client.get(f"{self.url}?scope=mine&category=letters")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "My demand letter")
        self.assertContains(response, "Rename")
        self.assertContains(response, "Delete")
        self.assertContains(response, "Edit")

    def test_upload_reaches_google_drive_and_stays_on_the_page(self):
        with patch(
            f"{VIEWS}.upload_drive_file", return_value={"id": "file-id"}
        ) as upload:
            response = self.client.post(self.url, self.upload_payload())

        upload.assert_called_once()
        self.assertEqual(upload.call_args.kwargs["parent_id"], "letters-id")
        self.assertEqual(upload.call_args.kwargs["name"], "Engagement letter")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            f"{self.url}?scope=company&category=letters#templates-forms-library",
        )

    def test_successful_upload_notifies_the_user(self):
        with patch(f"{VIEWS}.upload_drive_file", return_value={"id": "file-id"}):
            response = self.client.post(self.url, self.upload_payload(), follow=True)

        self.assertContains(response, "uploaded under Company templates")
        self.assertContains(response, "Engagement letter")

    def test_upload_to_my_templates_uses_personal_folder(self):
        with patch(
            f"{VIEWS}.upload_drive_file", return_value={"id": "mine-file"}
        ) as upload:
            response = self.client.post(
                self.url,
                self.upload_payload(scope="mine", title="Personal letter"),
            )

        upload.assert_called_once()
        self.assertEqual(upload.call_args.kwargs["parent_id"], "my-letters-id")
        self.assertEqual(
            response["Location"],
            f"{self.url}?scope=mine&category=letters#templates-forms-library",
        )

    def test_failed_upload_explains_why_without_leaving_the_page(self):
        with patch(
            f"{VIEWS}.upload_drive_file",
            side_effect=GoogleDriveAPIError("Google Drive upload failed (403)."),
        ):
            response = self.client.post(self.url, self.upload_payload())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Google Drive upload failed (403).")
        self.assertContains(response, "templates-and-forms-page")

    def test_missing_file_reports_the_reason(self):
        response = self.client.post(
            self.url,
            {
                "template_action": "upload",
                "scope": "company",
                "category": "letters",
                "title": "Engagement letter",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Nothing was uploaded.")
        self.assertContains(response, "Choose a file to upload.")

    def test_create_google_template_lands_on_the_library(self):
        with patch(
            f"{VIEWS}.create_google_workspace_file",
            return_value={"id": "doc-id", "_workspace_label": "Google Doc"},
        ) as create, patch(f"{VIEWS}.apply_company_letterhead_to_google_doc"):
            response = self.client.post(
                self.url,
                {
                    "template_action": "create_google",
                    "scope": "company",
                    "category": "letters",
                    "title": "Demand letter",
                    "google_type": "document",
                    "include_letterhead": "on",
                },
            )

        create.assert_called_once()
        self.assertEqual(create.call_args.kwargs["parent_id"], "letters-id")
        self.assertEqual(
            response["Location"],
            f"{self.url}?scope=company&category=letters#templates-forms-library",
        )

    def test_create_failure_reports_the_drive_reason(self):
        with patch(
            f"{VIEWS}.create_google_workspace_file",
            side_effect=GoogleDriveAPIError("Drive quota exceeded."),
        ):
            response = self.client.post(
                self.url,
                {
                    "template_action": "create_google",
                    "scope": "company",
                    "category": "letters",
                    "title": "Demand letter",
                    "google_type": "document",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Drive quota exceeded.")

    def test_disconnected_drive_blocks_the_upload_with_a_reason(self):
        self.connection.access_token = ""
        self.connection.refresh_token = ""
        self.connection.save()

        with patch(f"{VIEWS}.upload_drive_file") as upload:
            response = self.client.post(self.url, self.upload_payload())

        upload.assert_not_called()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Connect Google Drive before creating")

    def test_duplicate_company_template_into_my_templates(self):
        with (
            patch(
                f"{VIEWS}._assert_template_in_category",
                return_value={
                    "id": "company-letter-id",
                    "name": "Company demand letter",
                },
            ),
            patch(
                f"{VIEWS}.copy_drive_file",
                return_value={
                    "id": "copy-id",
                    "name": "Company demand letter (copy)",
                },
            ) as copy_mock,
        ):
            response = self.client.post(
                self.url,
                {
                    "template_action": "duplicate",
                    "scope": "company",
                    "category": "letters",
                    "file_id": "company-letter-id",
                    "title": "Company demand letter (copy)",
                },
            )

        copy_mock.assert_called_once_with(
            "company-letter-id",
            name="Company demand letter (copy)",
            parent_id="my-letters-id",
        )
        self.assertEqual(
            response["Location"],
            f"{self.url}?scope=mine&category=letters#templates-forms-library",
        )

    def test_rename_my_template(self):
        with (
            patch(
                f"{VIEWS}.get_drive_file_meta",
                return_value={
                    "id": "my-letter-id",
                    "name": "My demand letter",
                    "parents": ["my-letters-id"],
                    "trashed": False,
                },
            ),
            patch(f"{VIEWS}.rename_drive_file") as rename_mock,
        ):
            response = self.client.post(
                self.url,
                {
                    "template_action": "rename",
                    "scope": "mine",
                    "category": "letters",
                    "file_id": "my-letter-id",
                    "title": "Renamed letter",
                },
            )

        rename_mock.assert_called_once_with("my-letter-id", "Renamed letter")
        self.assertEqual(
            response["Location"],
            f"{self.url}?scope=mine&category=letters#templates-forms-library",
        )

    def test_delete_my_template(self):
        with (
            patch(
                f"{VIEWS}.get_drive_file_meta",
                return_value={
                    "id": "my-letter-id",
                    "name": "My demand letter",
                    "parents": ["my-letters-id"],
                    "trashed": False,
                },
            ),
            patch(f"{VIEWS}.trash_drive_file") as trash_mock,
        ):
            response = self.client.post(
                self.url,
                {
                    "template_action": "delete",
                    "scope": "mine",
                    "category": "letters",
                    "file_id": "my-letter-id",
                },
            )

        trash_mock.assert_called_once_with("my-letter-id")
        self.assertEqual(
            response["Location"],
            f"{self.url}?scope=mine&category=letters#templates-forms-library",
        )

    def test_cannot_delete_company_template_from_company_scope(self):
        with patch(f"{VIEWS}.trash_drive_file") as trash_mock:
            response = self.client.post(
                self.url,
                {
                    "template_action": "delete",
                    "scope": "company",
                    "category": "letters",
                    "file_id": "company-letter-id",
                },
                follow=True,
            )

        trash_mock.assert_not_called()
        self.assertContains(response, "Only personal templates can be deleted")
