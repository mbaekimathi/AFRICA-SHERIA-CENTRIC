"""Workspace middleware for employee session tracking and access locks."""

from django.contrib.auth import logout
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.deprecation import MiddlewareMixin

from .employee_sessions import (
    end_employee_session,
    touch_employee_session,
)
from .models import Employee, EmployeeWorkSession


class EmployeeSessionMiddleware(MiddlewareMixin):
    """Keep work sessions active; force-logout suspended employees immediately."""

    def process_request(self, request):
        if request.path.startswith(("/static/", "/media/")):
            return None

        user = getattr(request, "user", None)
        if (
            getattr(user, "is_authenticated", False)
            and isinstance(user, Employee)
            and user.status == Employee.Status.SUSPENDED
        ):
            end_employee_session(
                request,
                kind=EmployeeWorkSession.LogoutKind.SUSPENDED,
            )
            logout(request)
            request.session["show_suspended_modal"] = "session"
            login_path = reverse("accounts:login")
            if request.path != login_path:
                return redirect(login_path)
            return None

        touch_employee_session(request)
        return None
