"""Session-based auth for Client accounts (separate from Employee AUTH_USER_MODEL)."""

from django.utils import timezone

from .models import Client

SESSION_KEY = "client_id"


def login_client(request, client: Client) -> None:
    request.session[SESSION_KEY] = client.pk
    request.session.cycle_key()
    Client.objects.filter(pk=client.pk).update(last_login=timezone.now())
    client.last_login = timezone.now()


def logout_client(request) -> None:
    request.session.pop(SESSION_KEY, None)


def get_client(request) -> Client | None:
    client_id = request.session.get(SESSION_KEY)
    if not client_id:
        return None
    try:
        return Client.objects.get(pk=client_id)
    except Client.DoesNotExist:
        request.session.pop(SESSION_KEY, None)
        return None


def redirect_for_client(client: Client):
    from django.shortcuts import redirect

    if client.status == Client.Status.PENDING_ONBOARDING:
        return redirect("accounts:client_onboarding")
    if client.status == Client.Status.PENDING_APPROVAL:
        return redirect("accounts:client_pending")
    if client.status == Client.Status.ACTIVE:
        return redirect("accounts:client_dashboard")
    return redirect("accounts:client_login")
