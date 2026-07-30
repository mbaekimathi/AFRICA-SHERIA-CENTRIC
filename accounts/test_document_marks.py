import json

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import (
    Client,
    Document,
    DocumentMark,
    Employee,
    LitigationCase,
)


class DocumentMarkPlacementTests(TestCase):
    def setUp(self):
        self.user = Employee.objects.create_user(
            login_code="778899",
            password="test-pass-123",
            first_name="Signing",
            last_name="Advocate",
            personal_email="signing.advocate@example.com",
            role=Employee.Role.MANAGING_PARTNER,
            status=Employee.Status.ACTIVE,
        )
        self.client.force_login(self.user)
        client_person = Client.objects.create(
            email="mark.client@example.com",
            first_name="Mark",
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
        self.document = Document.objects.create(
            case=self.case,
            title="Plaint",
            source=Document.Source.GOOGLE_DOC,
            drive_file_id="drive-plaint-id",
            mime_type="application/vnd.google-apps.document",
            uploaded_by=self.user,
        )
        self.case_url = reverse(
            "accounts:view_litigation_case",
            kwargs={"role": self.user.role_slug, "case_id": self.case.pk},
        )
        self.marks_url = reverse(
            "accounts:document_marks",
            kwargs={
                "role": self.user.role_slug,
                "document_id": self.document.pk,
            },
        )
        self.editor_url = reverse(
            "accounts:place_document_marks",
            kwargs={
                "role": self.user.role_slug,
                "document_id": self.document.pk,
            },
        )

    def _place(self, payload):
        return self.client.post(
            self.marks_url,
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_case_page_offers_stamp_and_signature_checkboxes(self):
        response = self.client.get(self.case_url)

        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn(
            'data-doc-mark-editor-url="%s?mark=signature"' % self.editor_url,
            body,
        )
        self.assertIn(
            'data-doc-mark-editor-url="%s?mark=stamp"' % self.editor_url,
            body,
        )
        self.assertIn("Place on document", body)

    def test_editor_uses_the_actual_document_as_the_drag_surface(self):
        response = self.client.get(f"{self.editor_url}?mark=signature")

        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn("data-doc-marks-page", body)
        self.assertIn("data-doc-marks-sheet", body)
        self.assertIn("data-doc-marks-layer", body)
        self.assertIn("drive-plaint-id/preview", body)
        self.assertIn('data-initial-kind="signature"', body)
        self.assertIn('data-doc-mark-source="stamp"', body)

    def test_placement_is_saved_for_the_session_user(self):
        response = self._place(
            {"kind": "stamp", "page": 2, "x": 55.5, "y": 61.25, "width": 18}
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["created"])
        mark = DocumentMark.objects.get(
            document=self.document, employee=self.user, kind="stamp"
        )
        self.assertEqual(mark.page, 2)
        self.assertAlmostEqual(mark.x_percent, 55.5)
        self.assertAlmostEqual(mark.width_percent, 18)

    def test_moving_a_mark_updates_the_existing_row(self):
        self._place({"kind": "signature", "x": 10, "y": 70, "width": 30})
        self._place({"kind": "signature", "x": 40, "y": 20, "width": 25})

        marks = DocumentMark.objects.filter(document=self.document)
        self.assertEqual(marks.count(), 1)
        self.assertAlmostEqual(marks.first().x_percent, 40)

    def test_out_of_range_positions_are_clamped(self):
        self._place({"kind": "stamp", "x": -20, "y": 480, "width": 0})

        mark = DocumentMark.objects.get(document=self.document, kind="stamp")
        self.assertEqual(mark.x_percent, 0)
        self.assertEqual(mark.y_percent, 100)
        self.assertEqual(mark.width_percent, 4)

    def test_unchecking_removes_the_mark(self):
        self._place({"kind": "stamp", "x": 60, "y": 70, "width": 20})

        response = self._place({"kind": "stamp", "remove": True})

        self.assertTrue(response.json()["removed"])
        self.assertFalse(DocumentMark.objects.filter(kind="stamp").exists())

    def test_unknown_mark_kind_is_rejected(self):
        response = self._place({"kind": "initials", "x": 10, "y": 10})

        self.assertEqual(response.status_code, 400)
        self.assertFalse(DocumentMark.objects.exists())

    def test_saved_marks_come_back_checked_on_the_case_page(self):
        self._place({"kind": "signature", "x": 12, "y": 66, "width": 28})

        response = self.client.get(self.case_url)

        body = response.content.decode()
        self.assertIn(
            'data-doc-mark-editor-url="%s?mark=signature"' % self.editor_url,
            body,
        )
        self.assertContains(response, "checked")
