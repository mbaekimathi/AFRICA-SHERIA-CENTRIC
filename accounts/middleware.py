"""Workspace middleware for employee session tracking."""

from django.utils.deprecation import MiddlewareMixin

from .employee_sessions import touch_employee_session


class EmployeeSessionMiddleware(MiddlewareMixin):
    """Keep employee work sessions active while the workspace is in use."""

    def process_request(self, request):
        if request.path.startswith(("/static/", "/media/")):
            return None
        touch_employee_session(request)
        return None
