from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from accounts.models import (
    CaseTask,
    Client,
    CourtAttendance,
    Employee,
    LitigationCase,
)
from accounts.workspace import (
    matter_desk_welcome_stats,
    set_employee_activity_permission,
)


class MatterDeskWelcomeStatsTests(TestCase):
    def setUp(self):
        self.viewer = Employee.objects.create_user(
            login_code="333333",
            password="test-pass-123",
            first_name="Desk",
            last_name="Viewer",
            personal_email="desk.viewer@example.com",
            role=Employee.Role.ADVOCATE,
            status=Employee.Status.ACTIVE,
        )
        self.other = Employee.objects.create_user(
            login_code="444444",
            password="test-pass-123",
            first_name="Other",
            last_name="Counsel",
            personal_email="other.counsel@example.com",
            role=Employee.Role.ADVOCATE,
            status=Employee.Status.ACTIVE,
        )
        self.client_person = Client.objects.create(
            email="desk.client@example.com",
            first_name="Desk",
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
            assigned_to=self.viewer,
        )
        self.other_case = LitigationCase.objects.create(
            filing_date=today,
            client=self.client_person,
            court_rank="high_court",
            case_category="civil",
            case_type="suit",
            station="nairobi",
            status=LitigationCase.Status.ACTIVE,
            assigned_to=self.other,
        )
        CourtAttendance.objects.create(
            case=self.own_case,
            activity_type="Mention",
            judicial_officer="Hon. Test",
            attendance_date=today - timedelta(days=7),
            next_court_date=today + timedelta(days=14),
            recorded_by=self.viewer,
        )
        CourtAttendance.objects.create(
            case=self.other_case,
            activity_type="Hearing",
            judicial_officer="Hon. Test",
            attendance_date=today - timedelta(days=3),
            next_court_date=today + timedelta(days=21),
            recorded_by=self.other,
        )
        CaseTask.objects.create(
            case=self.own_case,
            assignee=self.viewer,
            title="Own task",
            due_date=today + timedelta(days=3),
            created_by=self.other,
            status=CaseTask.Status.ACCEPTED,
        )
        CaseTask.objects.create(
            case=self.other_case,
            assignee=self.other,
            title="Other task",
            due_date=today + timedelta(days=5),
            created_by=self.viewer,
            status=CaseTask.Status.PENDING,
        )

    def _stat_map(self, user):
        return {card["key"]: card["value"] for card in matter_desk_welcome_stats(user)}

    def test_view_all_counts_every_visible_matter(self):
        stats = self._stat_map(self.viewer)
        self.assertEqual(stats["my-matters"], 2)
        self.assertEqual(stats["upcoming-hearings"], 2)
        # Tasks default to assignee-only (View all off).
        self.assertEqual(stats["tasks-and-progress"], 1)

    def test_locking_view_all_limits_dashboard_counts(self):
        for slug in ("litigation-matters", "non-litigation-matters"):
            set_employee_activity_permission(
                employee_id=self.viewer.pk,
                module_slug="matter-management",
                activity_slug=slug,
                action="view_all",
                is_allowed=False,
                updated_by=None,
            )
        stats = self._stat_map(self.viewer)
        self.assertEqual(stats["my-matters"], 1)
        self.assertEqual(stats["upcoming-hearings"], 1)
        self.assertEqual(stats["tasks-and-progress"], 1)

    def test_all_metric_cards_are_interactive(self):
        cards = matter_desk_welcome_stats(self.viewer)
        self.assertEqual(len(cards), 3)
        for card in cards:
            self.assertTrue(card["interactive"], card["key"])
            self.assertIn("items", card)
            self.assertTrue(card.get("view_all_url"))

    def test_upcoming_hearings_dropdown_lists_visible_items(self):
        cards = {card["key"]: card for card in matter_desk_welcome_stats(self.viewer)}
        hearings = cards["upcoming-hearings"]
        self.assertEqual(hearings["value"], 2)
        self.assertEqual(len(hearings["items"]), 2)
        self.assertTrue(all(item["url"] for item in hearings["items"]))
