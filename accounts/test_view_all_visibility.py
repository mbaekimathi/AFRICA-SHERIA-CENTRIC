from django.test import TestCase
from django.utils import timezone

from accounts.models import (
    Client,
    Employee,
    EmployeeActivityPermission,
    LitigationCase,
)
from accounts.workspace import (
    cases_visible_to,
    employee_can_access_case,
    employee_can_view_all,
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
        self.assertEqual(visible, {self.own_case.pk, self.other_case.pk})

    def test_locking_view_all_limits_to_allocated(self):
        set_employee_activity_permission(
            employee_id=self.assignee.pk,
            module_slug="matter-management",
            activity_slug="litigation-matters",
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
            activity_slug="litigation-matters",
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
            activity_slug="litigation-matters",
            action="view_all",
        )
        self.assertFalse(row.is_allowed)
        set_employee_activity_permission(
            employee_id=self.assignee.pk,
            module_slug="matter-management",
            activity_slug="litigation-matters",
            action="view_all",
            is_allowed=True,
            updated_by=None,
        )
        self.assertTrue(employee_can_view_all(self.assignee, "litigation-matters"))
