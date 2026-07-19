"""Google ID token verification for client sign-in."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings


class GoogleAuthError(Exception):
    pass


def verify_google_id_token(id_token: str) -> dict:
    """
    Verify a Google Identity Services ID token via Google's tokeninfo endpoint.
    Returns claims: sub, email, email_verified, given_name, family_name, picture, ...
    """
    client_id = getattr(settings, "GOOGLE_CLIENT_ID", "") or ""
    if not client_id:
        raise GoogleAuthError("Google sign-in is not configured.")

    token = (id_token or "").strip()
    if not token:
        raise GoogleAuthError("Missing Google credential.")

    # Prefer POST so long JWTs are not truncated by URL length limits.
    body = urllib.parse.urlencode({"id_token": token}).encode("utf-8")
    request = urllib.request.Request(
        "https://oauth2.googleapis.com/tokeninfo",
        data=body,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="ignore")[:200]
        except Exception:
            pass
        if exc.code in (400, 401):
            raise GoogleAuthError("Google sign-in expired or was invalid. Try again.") from exc
        raise GoogleAuthError(
            f"Could not verify Google sign-in ({exc.code}). {detail}".strip()
        ) from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise GoogleAuthError("Could not verify Google sign-in.") from exc

    if payload.get("aud") != client_id:
        raise GoogleAuthError("Google credential audience mismatch.")
    if payload.get("email_verified") not in (True, "true", "True"):
        raise GoogleAuthError("Google email is not verified.")
    if not payload.get("email"):
        raise GoogleAuthError("Google account has no email.")

    return payload
