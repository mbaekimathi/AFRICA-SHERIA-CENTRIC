from django.test import TestCase
from django.utils import timezone

from accounts.models import (
    Client,
    Document,
    Employee,
    EmployeeActivityPermission,
    LitigationCase,
)
from accounts.workspace import (
    cases_visible_to,
    employee_can_access_case,
    employee_can_access_case_documents,
    employee_can_access_document,
    employee_can_view_all,
    matter_visibility_revision,
    pending_litigation_cases_count,
    set_employee_activity_permission,
)


class ViewAllVisibilityTests(TestCase):
    def setUp(self):
        self.viewer = Employee.objects.create_user(
            login_code="111111",
            password="test-pass-123",
            first_name="View",
            last_name="Only",
            personal_email="viewer@example.com",
            role=Employee.Role.ADVOCATE,
            status=Employee.Status.ACTIVE,
        )
        self.assignee = Employee.objects.create_user(
            login_code="222222",
            password="test-pass-123",
            first_name="Assigned",
            last_name="Advocate",
            personal_email="assignee@example.com",
            role=Employee.Role.ADVOCATE,
            status=Employee.Status.ACTIVE,
        )
        self.client_person = Client.objects.create(
            email="pat.client@example.com",
            first_name="Pat",
            last_name="Client",
            status=Client.Status.ACTIVE,
        )
        today = timezone.localdate()
        self.own_case = LitigationCase.objects.create(
            filing_date=today,
            client=self.client_person,
            court_rank="high_court",
            case_category="civil",
            case_type="suit",
            station="nairobi",
            status=LitigationCase.Status.ACTIVE,
            assigned_to=self.assignee,
        )
        self.other_case = LitigationCase.objects.create(
            filing_date=today,
            client=self.client_person,
            court_rank="high_court",
            case_category="civil",
            case_type="suit",
            station="nairobi",
            status=LitigationCase.Status.ACTIVE,
            assigned_to=self.viewer,
        )
        # Registered by assignee but allocated to someone else — must stay hidden
        # when View all is locked (registration alone is not allocation).
        self.registered_but_reallocated = LitigationCase.objects.create(
            filing_date=today,
            client=self.client_person,
            court_rank="high_court",
            case_category="civil",
            case_type="suit",
            station="nairobi",
            status=LitigationCase.Status.ACTIVE,
            assigned_to=self.viewer,
            registered_by=self.assignee,
        )
        self.own_pending = LitigationCase.objects.create(
            filing_date=today,
            client=self.client_person,
            court_rank="high_court",
            case_category="civil",
            case_type="suit",
            station="nairobi",
            status=LitigationCase.Status.PENDING_APPROVAL,
            registered_by=self.assignee,
        )
        self.other_pending = LitigationCase.objects.create(
            filing_date=today,
            client=self.client_person,
            court_rank="high_court",
            case_category="civil",
            case_type="suit",
            station="nairobi",
            status=LitigationCase.Status.PENDING_APPROVAL,
            registered_by=self.viewer,
        )

    def test_default_view_all_shows_every_active_case(self):
        self.assertTrue(employee_can_view_all(self.assignee, "litigation-matters"))
        visible = set(
            cases_visible_to(
                self.assignee, status=LitigationCase.Status.ACTIVE
            ).values_list("pk", flat=True)
        )
        self.assertEqual(
            visible,
            {
                self.own_case.pk,
                self.other_case.pk,
                self.registered_but_reallocated.pk,
            },
        )

    def test_locking_view_all_limits_to_allocated(self):
        set_employee_activity_permission(
            employee_id=self.assignee.pk,
            module_slug="matter-management",
            activity_slug="matter-management",
            action="view_all",
            is_allowed=False,
            updated_by=None,
        )
        self.assertFalse(employee_can_view_all(self.assignee, "litigation-matters"))
        visible = list(
            cases_visible_to(
                self.assignee, status=LitigationCase.Status.ACTIVE
            ).values_list("pk", flat=True)
        )
        self.assertEqual(visible, [self.own_case.pk])
        self.assertTrue(employee_can_access_case(self.assignee, self.own_case))
        self.assertFalse(employee_can_access_case(self.assignee, self.other_case))
        self.assertFalse(
            employee_can_access_case(self.assignee, self.registered_but_reallocated)
        )

    def test_default_view_all_shows_every_pending_case(self):
        visible = set(
            cases_visible_to(
                self.assignee, status=LitigationCase.Status.PENDING_APPROVAL
            ).values_list("pk", flat=True)
        )
        self.assertEqual(visible, {self.own_pending.pk, self.other_pending.pk})
        self.assertEqual(pending_litigation_cases_count(self.assignee), 2)

    def test_locking_view_all_limits_pending_to_registered(self):
        set_employee_activity_permission(
            employee_id=self.assignee.pk,
            module_slug="matter-management",
            activity_slug="matter-management",
            action="view_all",
            is_allowed=False,
            updated_by=None,
        )
        visible = list(
            cases_visible_to(
                self.assignee, status=LitigationCase.Status.PENDING_APPROVAL
            ).values_list("pk", flat=True)
        )
        self.assertEqual(visible, [self.own_pending.pk])
        self.assertEqual(pending_litigation_cases_count(self.assignee), 1)
        self.assertTrue(employee_can_access_case(self.assignee, self.own_pending))
        self.assertFalse(employee_can_access_case(self.assignee, self.other_pending))

    def test_permission_row_round_trip(self):
        set_employee_activity_permission(
            employee_id=self.assignee.pk,
            module_slug="matter-management",
            activity_slug="litigation-matters",
            action="view_all",
            is_allowed=False,
            updated_by=None,
        )
        row = EmployeeActivityPermission.objects.get(
            employee=self.assignee,
            module_slug="matter-management",
            activity_slug="matter-management",
            action="view_all",
        )
        self.assertFalse(row.is_allowed)
        self.assertFalse(employee_can_view_all(self.assignee, "non-litigation-matters"))
        set_employee_activity_permission(
            employee_id=self.assignee.pk,
            module_slug="matter-management",
            activity_slug="non-litigation-matters",
            action="view_all",
            is_allowed=True,
            updated_by=None,
        )
        self.assertTrue(employee_can_view_all(self.assignee, "litigation-matters"))
        self.assertTrue(employee_can_view_all(self.assignee, "non-litigation-matters"))

    def test_matter_visibility_revision_changes_when_view_all_locked(self):
        before = matter_visibility_revision(self.assignee)
        set_employee_activity_permission(
            employee_id=self.assignee.pk,
            module_slug="matter-management",
            activity_slug="matter-management",
            action="view_all",
            is_allowed=False,
            updated_by=None,
        )
        after = matter_visibility_revision(self.assignee)
        self.assertNotEqual(before, after)

    def test_matter_visibility_revision_changes_when_allocation_moves(self):
        set_employee_activity_permission(
            employee_id=self.assignee.pk,
            module_slug="matter-management",
            activity_slug="matter-management",
            action="view_all",
            is_allowed=False,
            updated_by=None,
        )
        before = matter_visibility_revision(self.assignee)
        self.own_case.assigned_to = self.viewer
        self.own_case.save(update_fields=["assigned_to", "updated_at"])
        after = matter_visibility_revision(self.assignee)
        self.assertNotEqual(before, after)

    def test_default_documents_view_all_allows_any_visible_case(self):
        self.assertTrue(employee_can_view_all(self.assignee, "matter-documents"))
        own_doc = Document.objects.create(
            case=self.own_case,
            title="Own brief",
            source=Document.Source.UPLOADED,
        )
        other_doc = Document.objects.create(
            case=self.other_case,
            title="Other brief",
            source=Document.Source.UPLOADED,
        )
        self.assertTrue(
            employee_can_access_case_documents(self.assignee, self.own_case)
        )
        self.assertTrue(
            employee_can_access_case_documents(self.assignee, self.other_case)
        )
        self.assertTrue(employee_can_access_document(self.assignee, own_doc))
        self.assertTrue(employee_can_access_document(self.assignee, other_doc))

    def test_locking_documents_view_all_limits_to_allocated(self):
        set_employee_activity_permission(
            employee_id=self.assignee.pk,
            module_slug="matter-management",
            activity_slug="matter-documents",
            action="view_all",
            is_allowed=False,
            updated_by=None,
        )
        self.assertFalse(employee_can_view_all(self.assignee, "matter-documents"))
        # Matter View all remains on — case list stays firm-wide.
        self.assertTrue(employee_can_view_all(self.assignee, "litigation-matters"))
        self.assertTrue(employee_can_access_case(self.assignee, self.other_case))
        self.assertTrue(
            employee_can_access_case_documents(self.assignee, self.own_case)
        )
        self.assertFalse(
            employee_can_access_case_documents(self.assignee, self.other_case)
        )
        other_doc = Document.objects.create(
            case=self.other_case,
            title="Other brief",
            source=Document.Source.UPLOADED,
        )
        self.assertFalse(employee_can_access_document(self.assignee, other_doc))
