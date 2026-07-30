from django.test import TestCase

from accounts.models import Employee
from accounts.workspace import (
    role_activity_is_allowed,
    set_role_activity_permission,
    workspace_context,
    workspace_module_visible,
)


def nav_slugs(context):
    return [item["slug"] for item in context["page_nav_items"]]


class RoleActivitySidebarTests(TestCase):
    def setUp(self):
        self.admin = Employee.objects.create_user(
            login_code="900001",
            password="test-pass-123",
            first_name="Ada",
            last_name="Admin",
            personal_email="ada@example.com",
            role=Employee.Role.FIRM_ADMIN,
            status=Employee.Status.ACTIVE,
        )
        self.advocate = Employee.objects.create_user(
            login_code="900002",
            password="test-pass-123",
            first_name="Ben",
            last_name="Counsel",
            personal_email="ben@example.com",
            role=Employee.Role.ADVOCATE,
            status=Employee.Status.ACTIVE,
        )

    def lock(self, role, module_slug, activity_slug):
        set_role_activity_permission(
            role=role,
            module_slug=module_slug,
            activity_slug=activity_slug,
            is_allowed=False,
        )

    def section_nav(self, user, *trail):
        return nav_slugs(
            workspace_context(
                user,
                page_title="Page",
                page_trail=list(trail),
                active_page=trail[-1],
            )
        )

    def test_locked_activity_leaves_the_section_nav(self):
        self.lock(Employee.Role.FIRM_ADMIN, "user-management", "client-management")

        self.assertNotIn(
            "client-management", self.section_nav(self.admin, "dashboard", "user-management")
        )
        self.assertIn(
            "client-management",
            self.section_nav(self.advocate, "dashboard", "user-management"),
        )

    def test_locked_activity_locks_its_subtree(self):
        self.lock(Employee.Role.FIRM_ADMIN, "user-management", "client-management")

        self.assertFalse(
            role_activity_is_allowed(
                Employee.Role.FIRM_ADMIN, "user-management", "register-client"
            )
        )
        self.assertTrue(
            role_activity_is_allowed(
                Employee.Role.FIRM_ADMIN, "user-management", "employee-management"
            )
        )
        self.assertTrue(
            role_activity_is_allowed(
                Employee.Role.ADVOCATE, "user-management", "register-client"
            )
        )

    def test_module_link_stays_while_one_activity_is_open(self):
        self.lock(Employee.Role.FIRM_ADMIN, "user-management", "client-management")

        self.assertTrue(workspace_module_visible(self.admin, "user-management"))
        self.assertIn(
            "user-management", self.section_nav(self.admin, "dashboard")
        )

    def test_module_link_leaves_dashboard_when_every_activity_is_locked(self):
        self.lock(Employee.Role.FIRM_ADMIN, "user-management", "client-management")
        self.lock(Employee.Role.FIRM_ADMIN, "user-management", "employee-management")

        self.assertFalse(workspace_module_visible(self.admin, "user-management"))
        dashboard_nav = self.section_nav(self.admin, "dashboard")
        self.assertNotIn("user-management", dashboard_nav)
        self.assertIn("matter-management", dashboard_nav)
        self.assertIn(
            "user-management", self.section_nav(self.advocate, "dashboard")
        )

    def test_matter_hub_lock_hides_the_module(self):
        self.lock(Employee.Role.FIRM_ADMIN, "matter-management", "matter-management")

        self.assertFalse(workspace_module_visible(self.admin, "matter-management"))
        self.assertNotIn(
            "matter-management", self.section_nav(self.admin, "dashboard")
        )


class RoleActivityAccessTests(TestCase):
    def setUp(self):
        self.admin = Employee.objects.create_user(
            login_code="900003",
            password="test-pass-123",
            first_name="Ada",
            last_name="Admin",
            personal_email="ada2@example.com",
            role=Employee.Role.FIRM_ADMIN,
            status=Employee.Status.ACTIVE,
        )
        self.client.force_login(self.admin)

    def test_locked_parent_blocks_a_nested_page(self):
        set_role_activity_permission(
            role=Employee.Role.FIRM_ADMIN,
            module_slug="user-management",
            activity_slug="client-management",
            is_allowed=False,
        )

        response = self.client.get(
            "/firm-administrator/dashboard/user-management/client-management/register-client/",
            follow=True,
        )

        self.assertEqual(
            response.redirect_chain[-1][0],
            "/firm-administrator/dashboard/user-management/",
        )

    def test_fully_locked_module_hub_is_blocked(self):
        for slug in ("client-management", "employee-management"):
            set_role_activity_permission(
                role=Employee.Role.FIRM_ADMIN,
                module_slug="user-management",
                activity_slug=slug,
                is_allowed=False,
            )

        response = self.client.get(
            "/firm-administrator/dashboard/user-management/", follow=True
        )

        self.assertEqual(
            response.redirect_chain[-1][0], "/firm-administrator/dashboard/"
        )

    def test_open_module_hub_still_renders(self):
        response = self.client.get("/firm-administrator/dashboard/user-management/")

        self.assertEqual(response.status_code, 200, response.get("Location", ""))
