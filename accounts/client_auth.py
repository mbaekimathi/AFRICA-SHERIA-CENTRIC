"""Session-based auth for Client accounts (separate from Employee AUTH_USER_MODEL)."""

from django.utils import timezone

from .models import Client

SESSION_KEY = "client_id"
STAFF_IMPERSONATING_KEY = "staff_impersonating_client"
STAFF_RETURN_URL_KEY = "staff_impersonation_return_url"


def login_client(request, client: Client, *, update_last_login: bool = True) -> None:
    request.session[SESSION_KEY] = client.pk
    request.session.cycle_key()
    if update_last_login:
        Client.objects.filter(pk=client.pk).update(last_login=timezone.now())
        client.last_login = timezone.now()
    from .appearance import sync_session_client_appearance

    sync_session_client_appearance(request, client)


def logout_client(request) -> None:
    from .appearance import clear_session_client_appearance

    request.session.pop(SESSION_KEY, None)
    clear_session_client_appearance(request)
    clear_staff_impersonation(request)


def get_client(request) -> Client | None:
    client_id = request.session.get(SESSION_KEY)
    if not client_id:
        return None
    try:
        return Client.objects.get(pk=client_id)
    except Client.DoesNotExist:
        request.session.pop(SESSION_KEY, None)
        return None


def is_staff_impersonating(request) -> bool:
    return bool(request.session.get(STAFF_IMPERSONATING_KEY))


def start_staff_impersonation(request, client: Client, *, return_url: str) -> None:
    """Sign the current session into the client portal as this client (staff only)."""
    request.session[STAFF_IMPERSONATING_KEY] = True
    request.session[STAFF_RETURN_URL_KEY] = return_url
    login_client(request, client, update_last_login=False)


def clear_staff_impersonation(request) -> None:
    request.session.pop(STAFF_IMPERSONATING_KEY, None)
    request.session.pop(STAFF_RETURN_URL_KEY, None)


def end_staff_impersonation(request) -> str | None:
    """Leave the client portal session and return the staff return URL if any."""
    return_url = request.session.get(STAFF_RETURN_URL_KEY)
    request.session.pop(SESSION_KEY, None)
    clear_staff_impersonation(request)
    return return_url


def redirect_for_client(client: Client):
    from django.shortcuts import redirect

    if client.status == Client.Status.PENDING_ONBOARDING:
        return redirect("accounts:client_onboarding")
    if client.status == Client.Status.PENDING_APPROVAL:
        return redirect("accounts:client_pending")
    if client.status == Client.Status.ACTIVE:
        return redirect("accounts:client_dashboard")
    return redirect("accounts:client_login")
