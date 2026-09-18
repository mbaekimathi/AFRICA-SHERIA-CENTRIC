"""M-Pesa STK Push helpers (Daraja when configured, otherwise simulated)."""

from __future__ import annotations

import base64
import json
import logging
import uuid
from datetime import datetime
from decimal import Decimal
from urllib import error, parse, request

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

MPESA_CALLBACK_PATH = "/integrations/mpesa/callback/"
MPESA_B2B_RESULT_PATH = "/integrations/mpesa/b2b/result/"
MPESA_B2B_TIMEOUT_PATH = "/integrations/mpesa/b2b/timeout/"
MPESA_BALANCE_RESULT_PATH = "/integrations/mpesa/balance/result/"
MPESA_BALANCE_TIMEOUT_PATH = "/integrations/mpesa/balance/timeout/"


class MpesaError(Exception):
    """Raised when an STK push or B2B transfer cannot be started."""


def _finance_settings():
    try:
        from .models import FinanceSettings

        return FinanceSettings.get_solo()
    except Exception:
        return None


def is_valid_mpesa_callback_url(url: str) -> bool:
    """
    Safaricom requires a public HTTPS callback (not localhost / private LAN).
    """
    raw = (url or "").strip()
    if not raw:
        return False
    try:
        parts = parse.urlparse(raw)
    except ValueError:
        return False
    if parts.scheme.lower() != "https":
        return False
    host = (parts.hostname or "").lower()
    if not host:
        return False
    if host in {"localhost", "127.0.0.1", "::1"}:
        return False
    if host.endswith(".local"):
        return False
    octets = host.split(".")
    if len(octets) == 4 and all(p.isdigit() for p in octets):
        a, b = int(octets[0]), int(octets[1])
        if a == 10:
            return False
        if a == 172 and 16 <= b <= 31:
            return False
        if a == 192 and b == 168:
            return False
        if a == 169 and b == 254:
            return False
    # Require a path (not bare domain root) — Safaricom rejects vague URLs.
    path = parts.path or ""
    return bool(path and path not in {"/"})


def get_mpesa_runtime_config() -> dict:
    """
    Resolve STK credentials from Finance Settings when STK is enabled.
    Falls back to env vars only when no finance settings row is available.
    """
    firm = _finance_settings()
    if firm is not None:
        if not firm.allow_mpesa or not firm.mpesa_stk_enabled:
            return {
                "source": "finance_settings",
                "enabled": False,
                "consumer_key": "",
                "consumer_secret": "",
                "passkey": "",
                "shortcode": "",
                "callback_url": "",
                "env": "sandbox",
                "transaction_type": "CustomerPayBillOnline",
                "stk_ready": False,
            }
        return {
            "source": "finance_settings",
            "enabled": True,
            "consumer_key": (firm.mpesa_consumer_key or "").strip(),
            "consumer_secret": (firm.mpesa_consumer_secret or "").strip(),
            "passkey": (firm.mpesa_passkey or "").strip(),
            "shortcode": firm.stk_business_shortcode,
            "callback_url": (firm.mpesa_callback_url or "").strip(),
            "env": (firm.mpesa_env or "sandbox").lower(),
            "transaction_type": firm.stk_transaction_type,
            "stk_ready": firm.stk_ready,
        }

    return {
        "source": "env",
        "enabled": True,
        "consumer_key": getattr(settings, "MPESA_CONSUMER_KEY", "") or "",
        "consumer_secret": getattr(settings, "MPESA_CONSUMER_SECRET", "") or "",
        "passkey": getattr(settings, "MPESA_PASSKEY", "") or "",
        "shortcode": getattr(settings, "MPESA_SHORTCODE", "") or "",
        "callback_url": getattr(settings, "MPESA_CALLBACK_URL", "") or "",
        "env": (getattr(settings, "MPESA_ENV", "sandbox") or "sandbox").lower(),
        "transaction_type": "CustomerPayBillOnline",
        "stk_ready": bool(
            getattr(settings, "MPESA_CONSUMER_KEY", "")
            and getattr(settings, "MPESA_CONSUMER_SECRET", "")
            and getattr(settings, "MPESA_SHORTCODE", "")
            and getattr(settings, "MPESA_PASSKEY", "")
        ),
    }


def mpesa_stk_allowed() -> bool:
    """Whether the firm allows sending STK pushes from the app."""
    firm = _finance_settings()
    if firm is None:
        return True
    if not firm.allow_mpesa:
        return False
    return bool(firm.mpesa_stk_enabled)


def mpesa_configured() -> bool:
    cfg = get_mpesa_runtime_config()
    if cfg["source"] == "finance_settings" and not cfg["enabled"]:
        return False
    return bool(
        cfg["consumer_key"]
        and cfg["consumer_secret"]
        and cfg["shortcode"]
        and cfg["passkey"]
    )


def get_mpesa_b2b_runtime_config() -> dict:
    """
    Resolve outbound B2B / B2C transfer credentials from Finance Settings.
    OAuth keys fall back to STK Push keys when B2B-specific fields are blank.
    """
    firm = _finance_settings()
    if firm is None:
        return {
            "source": "none",
            "enabled": False,
            "consumer_key": "",
            "consumer_secret": "",
            "shortcode": "",
            "initiator_name": "",
            "security_credential": "",
            "result_url": "",
            "timeout_url": "",
            "env": "sandbox",
            "to_paybill": False,
            "to_till": False,
            "to_phone": False,
            "b2b_ready": False,
        }

    if not firm.allow_mpesa or not firm.mpesa_b2b_enabled:
        return {
            "source": "finance_settings",
            "enabled": False,
            "consumer_key": "",
            "consumer_secret": "",
            "shortcode": "",
            "initiator_name": "",
            "security_credential": "",
            "result_url": "",
            "timeout_url": "",
            "env": (firm.mpesa_env or "sandbox").lower(),
            "to_paybill": False,
            "to_till": False,
            "to_phone": False,
            "b2b_ready": False,
        }

    return {
        "source": "finance_settings",
        "enabled": True,
        "consumer_key": firm.b2b_consumer_key,
        "consumer_secret": firm.b2b_consumer_secret,
        "shortcode": firm.b2b_source_shortcode,
        "initiator_name": (firm.mpesa_b2b_initiator_name or "").strip(),
        "security_credential": (firm.mpesa_b2b_security_credential or "").strip(),
        "result_url": (firm.mpesa_b2b_result_url or "").strip(),
        "timeout_url": (firm.mpesa_b2b_timeout_url or "").strip(),
        "env": (firm.mpesa_env or "sandbox").lower(),
        "to_paybill": bool(firm.mpesa_b2b_to_paybill),
        "to_till": bool(firm.mpesa_b2b_to_till),
        "to_phone": bool(firm.mpesa_b2b_to_phone),
        "b2b_ready": firm.b2b_ready,
    }


def mpesa_b2b_allowed() -> bool:
    """Whether the firm allows outbound M-Pesa B2B / B2C transfers."""
    firm = _finance_settings()
    if firm is None:
        return False
    if not firm.allow_mpesa:
        return False
    return bool(firm.mpesa_b2b_enabled)


def mpesa_b2b_configured() -> bool:
    cfg = get_mpesa_b2b_runtime_config()
    if not cfg["enabled"]:
        return False
    return bool(
        cfg["consumer_key"]
        and cfg["consumer_secret"]
        and cfg["shortcode"]
        and cfg["initiator_name"]
        and cfg["security_credential"]
        and cfg["result_url"]
        and cfg["timeout_url"]
        and (cfg["to_paybill"] or cfg["to_till"] or cfg["to_phone"])
    )


def normalize_msisdn(phone: str) -> str:
    """Normalize Kenyan numbers to 2547XXXXXXXX."""
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    if digits.startswith("254") and len(digits) == 12:
        return digits
    if digits.startswith("0") and len(digits) == 10:
        return "254" + digits[1:]
    if len(digits) == 9 and digits.startswith(("7", "1")):
        return "254" + digits
    raise MpesaError("Enter a valid Safaricom number, e.g. 07XX XXX XXX.")


def _daraja_base(env: str = "") -> str:
    resolved = (env or getattr(settings, "MPESA_ENV", "sandbox") or "sandbox").lower()
    if resolved == "production":
        return "https://api.safaricom.co.ke"
    return "https://sandbox.safaricom.co.ke"


def _access_token(cfg: dict) -> str:
    key = cfg["consumer_key"]
    secret = cfg["consumer_secret"]
    auth = base64.b64encode(f"{key}:{secret}".encode()).decode()
    url = f"{_daraja_base(cfg['env'])}/oauth/v1/generate?grant_type=client_credentials"
    req = request.Request(
        url,
        headers={"Authorization": f"Basic {auth}"},
        method="GET",
    )
    try:
        with request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode())
    except error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        logger.warning("M-Pesa token error: %s %s", exc.code, body)
        raise MpesaError("Could not authenticate with M-Pesa. Check API credentials.") from exc
    except error.URLError as exc:
        raise MpesaError("Could not reach M-Pesa. Try again shortly.") from exc

    token = (payload or {}).get("access_token") or ""
    if not token:
        raise MpesaError("M-Pesa did not return an access token.")
    return token


def _password_and_timestamp(shortcode: str, passkey: str) -> tuple[str, str]:
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    raw = f"{shortcode}{passkey}{timestamp}"
    password = base64.b64encode(raw.encode()).decode()
    return password, timestamp


def _resolve_callback_url(explicit: str, cfg: dict) -> str:
    candidates = [
        (explicit or "").strip(),
        (cfg.get("callback_url") or "").strip(),
        (getattr(settings, "MPESA_CALLBACK_URL", "") or "").strip(),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        if is_valid_mpesa_callback_url(candidate):
            return candidate
        logger.warning("Ignoring invalid M-Pesa CallBackURL: %s", candidate)

    raise MpesaError(
        "M-Pesa needs a public HTTPS callback URL before STK Push can run. "
        f"In Finance Settings set it to https://yourdomain.com{MPESA_CALLBACK_PATH} "
        "(localhost and http:// are not accepted by Safaricom)."
    )


def initiate_stk_push(
    *,
    phone: str,
    amount: Decimal,
    account_reference: str,
    description: str,
    callback_url: str = "",
) -> dict:
    """
    Start an STK push.

    Returns a dict with checkout_request_id, merchant_request_id, customer_message,
    and simulated=True when Daraja is not configured.
    """
    if not mpesa_stk_allowed():
        raise MpesaError(
            "M-Pesa STK Push is not enabled. Turn it on in Finance Settings."
        )

    msisdn = normalize_msisdn(phone)
    amount_int = int(Decimal(amount).quantize(Decimal("1")))
    if amount_int < 1:
        raise MpesaError("Payment amount must be at least KES 1.")

    reference = (account_reference or "INVOICE")[:12]
    desc = (description or "Invoice payment")[:20]
    cfg = get_mpesa_runtime_config()

    if not mpesa_configured():
        checkout_id = f"ws_CO_{uuid.uuid4().hex[:16]}"
        return {
            "simulated": True,
            "phone": msisdn,
            "amount": amount_int,
            "checkout_request_id": checkout_id,
            "merchant_request_id": f"sim-{uuid.uuid4().hex[:10]}",
            "customer_message": (
                "STK push simulated. Confirm on this page after the client enters their PIN."
            ),
            "response_code": "0",
            "started_at": timezone.now().isoformat(),
        }

    shortcode = cfg["shortcode"]
    passkey = cfg["passkey"]
    password, timestamp = _password_and_timestamp(shortcode, passkey)
    callback = _resolve_callback_url(callback_url, cfg)
    token = _access_token(cfg)
    body = {
        "BusinessShortCode": shortcode,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": cfg["transaction_type"],
        "Amount": amount_int,
        "PartyA": msisdn,
        "PartyB": shortcode,
        "PhoneNumber": msisdn,
        "CallBackURL": callback,
        "AccountReference": reference,
        "TransactionDesc": desc,
    }
    url = f"{_daraja_base(cfg['env'])}/mpesa/stkpush/v1/processrequest"
    req = request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=45) as resp:
            payload = json.loads(resp.read().decode())
    except error.HTTPError as exc:
        body_text = exc.read().decode(errors="replace")
        logger.warning("M-Pesa STK error: %s %s", exc.code, body_text)
        detail = ""
        try:
            err = json.loads(body_text)
            detail = (err.get("errorMessage") or err.get("errorCode") or "").strip()
        except (TypeError, ValueError, AttributeError):
            detail = ""
        if "callback" in detail.lower():
            raise MpesaError(
                "Safaricom rejected the callback URL. Use a public HTTPS URL such as "
                f"https://yourdomain.com{MPESA_CALLBACK_PATH}."
            ) from exc
        raise MpesaError(
            detail or "M-Pesa could not start the STK push. Try again."
        ) from exc
    except error.URLError as exc:
        raise MpesaError("Could not reach M-Pesa. Try again shortly.") from exc

    if str(payload.get("ResponseCode", "")) not in {"0", "00"}:
        raise MpesaError(
            payload.get("CustomerMessage")
            or payload.get("ResponseDescription")
            or "STK push was not accepted."
        )

    return {
        "simulated": False,
        "phone": msisdn,
        "amount": amount_int,
        "checkout_request_id": payload.get("CheckoutRequestID") or "",
        "merchant_request_id": payload.get("MerchantRequestID") or "",
        "customer_message": payload.get("CustomerMessage")
        or "Check your phone to enter your M-Pesa PIN.",
        "response_code": str(payload.get("ResponseCode") or ""),
        "started_at": timezone.now().isoformat(),
    }


def _callback_metadata_map(stk_callback: dict) -> dict:
    meta = (stk_callback or {}).get("CallbackMetadata") or {}
    items = meta.get("Item") or []
    out = {}
    for item in items:
        name = (item or {}).get("Name") or ""
        if name:
            out[name] = (item or {}).get("Value")
    return out


def parse_stk_callback_payload(payload: dict) -> dict:
    """Normalize a Daraja STK callback body into a status dict."""
    body = (payload or {}).get("Body") or {}
    stk = body.get("stkCallback") or {}
    result_code = str(stk.get("ResultCode", ""))
    meta = _callback_metadata_map(stk)
    receipt = str(meta.get("MpesaReceiptNumber") or "").strip()
    amount = meta.get("Amount")
    phone = str(meta.get("PhoneNumber") or "").strip()
    return {
        "checkout_request_id": (stk.get("CheckoutRequestID") or "").strip(),
        "merchant_request_id": (stk.get("MerchantRequestID") or "").strip(),
        "result_code": result_code,
        "result_desc": (stk.get("ResultDesc") or "").strip(),
        "mpesa_receipt": receipt,
        "amount": amount,
        "phone": phone,
        "success": result_code in {"0", "00"},
        "pending": False,
    }


def query_stk_status(*, checkout_request_id: str, simulated: bool = False) -> dict:
    """
    Query Daraja for STK result, or return a simulated success for sandbox UI testing.
    """
    checkout_id = (checkout_request_id or "").strip()
    if not checkout_id:
        raise MpesaError("Missing CheckoutRequestID for status check.")

    if simulated or not mpesa_configured():
        receipt = f"SIM{uuid.uuid4().hex[:8].upper()}"
        return {
            "checkout_request_id": checkout_id,
            "result_code": "0",
            "result_desc": "Simulated payment successful.",
            "mpesa_receipt": receipt,
            "success": True,
            "pending": False,
            "simulated": True,
        }

    cfg = get_mpesa_runtime_config()
    shortcode = cfg["shortcode"]
    passkey = cfg["passkey"]
    password, timestamp = _password_and_timestamp(shortcode, passkey)
    token = _access_token(cfg)
    body = {
        "BusinessShortCode": shortcode,
        "Password": password,
        "Timestamp": timestamp,
        "CheckoutRequestID": checkout_id,
    }
    url = f"{_daraja_base(cfg['env'])}/mpesa/stkpushquery/v1/query"
    req = request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=45) as resp:
            payload = json.loads(resp.read().decode())
    except error.HTTPError as exc:
        body_text = exc.read().decode(errors="replace")
        logger.warning("M-Pesa STK query error: %s %s", exc.code, body_text)
        # 500 "The transaction is being processed" often means still pending.
        if "being processed" in body_text.lower() or exc.code in {500, 404}:
            return {
                "checkout_request_id": checkout_id,
                "result_code": "",
                "result_desc": "Payment is still being processed. Try again shortly.",
                "mpesa_receipt": "",
                "success": False,
                "pending": True,
                "simulated": False,
            }
        raise MpesaError("Could not check M-Pesa payment status. Try again.") from exc
    except error.URLError as exc:
        raise MpesaError("Could not reach M-Pesa. Try again shortly.") from exc

    result_code = str(payload.get("ResultCode", ""))
    result_desc = (
        payload.get("ResultDesc")
        or payload.get("ResponseDescription")
        or ""
    ).strip()
    response_code = str(payload.get("ResponseCode", ""))

    # Request accepted but result not ready yet.
    if response_code in {"0", "00"} and result_code == "":
        return {
            "checkout_request_id": checkout_id,
            "result_code": "",
            "result_desc": result_desc or "Waiting for the customer to complete payment.",
            "mpesa_receipt": "",
            "success": False,
            "pending": True,
            "simulated": False,
        }

    success = result_code in {"0", "00"}
    pending = False
    # Common "still waiting" codes from Daraja query.
    if result_code in {"4999", "1037"} and "timeout" not in result_desc.lower():
        # 1037 can mean timeout — treat timeout as failed below
        pass
    if "being processed" in result_desc.lower() or "request cancelled" in "":
        pass
    if not success and (
        "being processed" in result_desc.lower()
        or result_code in {"", "4999"}
    ):
        pending = True

    return {
        "checkout_request_id": checkout_id,
        "result_code": result_code,
        "result_desc": result_desc
        or ("Payment successful." if success else "Payment was not completed."),
        "mpesa_receipt": "",
        "success": success,
        "pending": pending and not success,
        "simulated": False,
        "raw": payload,
    }


def create_stk_request(invoice=None, result=None, *, client=None, purpose=None):
    """Persist a newly initiated STK push for an invoice or client top-up."""
    from .models import MpesaStkRequest

    result = result or {}
    checkout_id = (result.get("checkout_request_id") or "").strip()
    if not checkout_id:
        raise MpesaError("M-Pesa did not return a CheckoutRequestID.")

    amount = Decimal(str(result.get("amount") or 0)).quantize(Decimal("0.01"))
    resolved_purpose = purpose or (
        MpesaStkRequest.Purpose.CLIENT_TOPUP
        if client is not None and invoice is None
        else MpesaStkRequest.Purpose.INVOICE_PAYMENT
    )
    if resolved_purpose == MpesaStkRequest.Purpose.INVOICE_PAYMENT and invoice is None:
        raise MpesaError("Invoice is required for invoice STK payments.")
    if resolved_purpose == MpesaStkRequest.Purpose.CLIENT_TOPUP and client is None:
        raise MpesaError("Client is required for account top-up STK payments.")

    obj, _ = MpesaStkRequest.objects.update_or_create(
        checkout_request_id=checkout_id,
        defaults={
            "invoice": invoice,
            "client": client or (getattr(invoice, "client", None) if invoice else None),
            "purpose": resolved_purpose,
            "merchant_request_id": (result.get("merchant_request_id") or "")[:128],
            "phone": (result.get("phone") or "")[:20],
            "amount": amount,
            "status": MpesaStkRequest.Status.PENDING,
            "result_code": "",
            "result_desc": "",
            "mpesa_receipt": "",
            "simulated": bool(result.get("simulated")),
            "payment_applied": False,
        },
    )
    return obj


def apply_stk_outcome(stk_request, outcome: dict):
    """
    Update STK request + invoice/client credit from a query/callback outcome.

    Returns a dict suitable for UI/session: status, receipt, reason, invoice_status, etc.
    """
    from django.db import transaction

    from .models import Client, ClientAccountTopup, MpesaStkRequest

    result_code = str(outcome.get("result_code") or "")
    result_desc = (outcome.get("result_desc") or "").strip()
    receipt = (outcome.get("mpesa_receipt") or "").strip()
    pending = bool(outcome.get("pending"))
    success = bool(outcome.get("success"))

    with transaction.atomic():
        stk = (
            MpesaStkRequest.objects.select_for_update()
            .select_related("invoice", "client")
            .get(pk=stk_request.pk)
        )
        invoice = stk.invoice
        client = stk.client

        def _payload(**extra):
            data = {
                "status": extra.get("status", stk.status),
                "result_code": extra.get("result_code", stk.result_code),
                "result_desc": extra.get("result_desc", stk.result_desc),
                "mpesa_receipt": extra.get("mpesa_receipt", stk.mpesa_receipt),
                "amount": str(stk.amount),
                "phone": stk.phone,
                "checkout_request_id": stk.checkout_request_id,
                "payment_applied": extra.get("payment_applied", stk.payment_applied),
                "purpose": stk.purpose,
                "invoice_status": "",
                "invoice_status_label": "",
                "amount_paid": "",
                "balance_due": "",
                "credit_balance": "",
            }
            if invoice is not None:
                data["invoice_status"] = invoice.status
                data["invoice_status_label"] = invoice.get_status_display()
                data["amount_paid"] = str(invoice.amount_paid)
                data["balance_due"] = str(invoice.balance_due)
            if client is not None:
                data["credit_balance"] = str(client.credit_balance)
                if stk.is_client_topup:
                    data["invoice_status_label"] = (
                        stk.result_desc
                        or f"Credit KES {client.credit_balance:,.2f}"
                    )
            for key, value in extra.items():
                if value is not None:
                    data[key] = value
            return data

        if pending:
            stk.result_desc = result_desc or stk.result_desc
            stk.save(update_fields=["result_desc", "updated_at"])
            return _payload(
                status="pending",
                result_code=result_code,
                result_desc=result_desc
                or "Waiting for the customer to enter their M-Pesa PIN.",
            )

        if success:
            stk.status = MpesaStkRequest.Status.SUCCESS
            stk.result_code = result_code or "0"
            stk.result_desc = (
                result_desc or "The service request is processed successfully."
            )
            if receipt:
                stk.mpesa_receipt = receipt[:64]
            elif not stk.mpesa_receipt and stk.simulated:
                stk.mpesa_receipt = f"SIM{uuid.uuid4().hex[:8].upper()}"
            stk.save(
                update_fields=[
                    "status",
                    "result_code",
                    "result_desc",
                    "mpesa_receipt",
                    "updated_at",
                ]
            )

            if not stk.payment_applied:
                if not stk.mpesa_receipt:
                    stk.mpesa_receipt = f"MPX{stk.checkout_request_id[-8:].upper()}"
                    stk.save(update_fields=["mpesa_receipt", "updated_at"])

                if stk.is_client_topup:
                    if client is None:
                        raise MpesaError("Client top-up STK is missing the client.")
                    topup = ClientAccountTopup.objects.filter(stk_request=stk).first()
                    result = client.apply_inbound_payment(
                        stk.amount,
                        mpesa_receipt=stk.mpesa_receipt,
                        note=(topup.note if topup else "") or "M-Pesa client payment",
                        method=ClientAccountTopup.Method.MPESA,
                        phone=stk.phone,
                        stk_request=stk,
                        created_by=getattr(topup, "created_by", None),
                    )
                    applied = Decimal(str(result["total"]))
                    parts = []
                    if result["applied_to_invoices"] > 0:
                        parts.append(
                            f"KES {result['applied_to_invoices']:,.2f} → "
                            f"{result['invoices_updated']} invoice(s)"
                        )
                    if result["credit_added"] > 0:
                        parts.append(
                            f"KES {result['credit_added']:,.2f} credit "
                            f"(now KES {result['credit_balance']:,.2f})"
                        )
                    elif not parts:
                        parts.append(
                            f"Credit KES {result['credit_balance']:,.2f}"
                        )
                    # Shown in STK success banner via invoice_status_label.
                    if parts:
                        stk.result_desc = "; ".join(parts)
                        stk.save(update_fields=["result_desc", "updated_at"])
                else:
                    if invoice is None:
                        raise MpesaError("Invoice STK is missing the invoice.")
                    applied, _new_status = invoice.apply_payment(
                        stk.amount,
                        mpesa_receipt=stk.mpesa_receipt,
                    )
                stk.payment_applied = True
                stk.save(update_fields=["payment_applied", "updated_at"])
            else:
                applied = Decimal("0.00")
                if invoice is not None:
                    invoice.refresh_from_db()
                if client is not None:
                    client.refresh_from_db(fields=["credit_balance"])

            return _payload(
                status="success",
                applied_amount=str(applied),
                payment_applied=True,
            )

        stk.status = MpesaStkRequest.Status.FAILED
        stk.result_code = result_code
        stk.result_desc = result_desc or "Payment failed."
        stk.save(
            update_fields=["status", "result_code", "result_desc", "updated_at"]
        )
        topup = ClientAccountTopup.objects.filter(stk_request=stk).first()
        if topup is not None and topup.status == ClientAccountTopup.Status.PENDING:
            topup.status = ClientAccountTopup.Status.FAILED
            topup.save(update_fields=["status", "updated_at"])
        return _payload(
            status="failed",
            result_code=stk.result_code,
            result_desc=stk.result_desc,
            mpesa_receipt="",
            payment_applied=False,
        )


def refresh_stk_request(stk_request):
    """
    Check payment status for an STK request (DB first, then Daraja query).
    """
    from .models import MpesaStkRequest

    stk_request.refresh_from_db()
    if stk_request.status == MpesaStkRequest.Status.SUCCESS:
        return apply_stk_outcome(
            stk_request,
            {
                "success": True,
                "pending": False,
                "result_code": stk_request.result_code or "0",
                "result_desc": stk_request.result_desc or "Payment successful.",
                "mpesa_receipt": stk_request.mpesa_receipt,
            },
        )
    if stk_request.status == MpesaStkRequest.Status.FAILED:
        return {
            "status": "failed",
            "result_code": stk_request.result_code,
            "result_desc": stk_request.result_desc or "Payment failed.",
            "mpesa_receipt": "",
            "amount": str(stk_request.amount),
            "phone": stk_request.phone,
            "checkout_request_id": stk_request.checkout_request_id,
            "invoice_status": stk_request.invoice.status,
            "invoice_status_label": stk_request.invoice.get_status_display(),
            "amount_paid": str(stk_request.invoice.amount_paid),
            "balance_due": str(stk_request.invoice.balance_due),
            "payment_applied": False,
        }

    outcome = query_stk_status(
        checkout_request_id=stk_request.checkout_request_id,
        simulated=stk_request.simulated,
    )
    # Prefer receipt already stored by callback.
    if outcome.get("success") and not outcome.get("mpesa_receipt") and stk_request.mpesa_receipt:
        outcome["mpesa_receipt"] = stk_request.mpesa_receipt
    return apply_stk_outcome(stk_request, outcome)


def process_stk_callback(payload: dict) -> dict | None:
    """Handle Daraja callback: update STK request and invoice when possible."""
    from .models import MpesaStkRequest

    parsed = parse_stk_callback_payload(payload)
    checkout_id = parsed.get("checkout_request_id") or ""
    if not checkout_id:
        return None

    try:
        stk = MpesaStkRequest.objects.select_related("invoice").get(
            checkout_request_id=checkout_id
        )
    except MpesaStkRequest.DoesNotExist:
        logger.warning("STK callback for unknown CheckoutRequestID=%s", checkout_id)
        return parsed

    if parsed.get("amount") is not None:
        try:
            amt = Decimal(str(parsed["amount"])).quantize(Decimal("0.01"))
            if amt > 0:
                stk.amount = amt
                stk.save(update_fields=["amount", "updated_at"])
        except Exception:
            pass

    return apply_stk_outcome(stk, parsed)


def _post_daraja_json(cfg: dict, path: str, payload: dict) -> dict:
    token = _access_token(cfg)
    url = f"{_daraja_base(cfg['env'])}{path}"
    body = json.dumps(payload).encode()
    req = request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=45) as resp:
            return json.loads(resp.read().decode())
    except error.HTTPError as exc:
        raw = exc.read().decode(errors="replace")
        logger.warning("Daraja HTTP %s %s: %s", exc.code, path, raw)
        try:
            detail = json.loads(raw)
            message = (
                detail.get("errorMessage")
                or detail.get("ResponseDescription")
                or detail.get("requestId")
                or raw
            )
        except Exception:
            message = raw or str(exc)
        raise MpesaError(f"M-Pesa request failed: {message}") from exc
    except error.URLError as exc:
        raise MpesaError("Could not reach M-Pesa. Try again shortly.") from exc


def _resolve_b2b_callback_urls(cfg: dict) -> tuple[str, str]:
    result = (cfg.get("result_url") or "").strip()
    timeout = (cfg.get("timeout_url") or "").strip()
    if not is_valid_mpesa_callback_url(result):
        raise MpesaError(
            "Set a public HTTPS B2B result URL in Finance Settings "
            f"(e.g. https://yourdomain.com{MPESA_B2B_RESULT_PATH})."
        )
    if not is_valid_mpesa_callback_url(timeout):
        raise MpesaError(
            "Set a public HTTPS B2B timeout URL in Finance Settings "
            f"(e.g. https://yourdomain.com{MPESA_B2B_TIMEOUT_PATH})."
        )
    return result, timeout


def initiate_b2b_transfer(
    *,
    destination_type: str,
    party_b: str,
    amount: Decimal,
    account_reference: str = "",
    remarks: str = "",
) -> dict:
    """
    Start an outbound B2B (Paybill/Till) or B2C (phone) transfer.

    Returns Daraja acknowledgement fields, with simulated=True when credentials
    are incomplete.
    """
    from .models import MpesaB2bTransfer

    if not mpesa_b2b_allowed():
        raise MpesaError(
            "M-Pesa B2B transfers are not enabled. Turn them on in Finance Settings."
        )

    cfg = get_mpesa_b2b_runtime_config()
    dest = (destination_type or "").strip().lower()
    if dest == MpesaB2bTransfer.DestinationType.PAYBILL and not cfg["to_paybill"]:
        raise MpesaError("Transfers to Paybill are disabled in Finance Settings.")
    if dest == MpesaB2bTransfer.DestinationType.TILL and not cfg["to_till"]:
        raise MpesaError("Transfers to Buy Goods Till are disabled in Finance Settings.")
    if dest == MpesaB2bTransfer.DestinationType.PHONE and not cfg["to_phone"]:
        raise MpesaError("Transfers to phone numbers are disabled in Finance Settings.")

    amount_int = int(Decimal(amount).quantize(Decimal("1")))
    if amount_int < 1:
        raise MpesaError("Transfer amount must be at least KES 1.")

    party = "".join(ch for ch in (party_b or "") if ch.isdigit())
    if dest == MpesaB2bTransfer.DestinationType.PHONE:
        party = normalize_msisdn(party_b)
    elif not party:
        raise MpesaError("Enter the destination Paybill or Till number.")

    reference = (account_reference or "").strip()[:13]
    note = (remarks or "Transfer").strip()[:100] or "Transfer"

    if not mpesa_b2b_configured():
        return {
            "simulated": True,
            "destination_type": dest,
            "party_b": party,
            "amount": amount_int,
            "account_reference": reference,
            "conversation_id": f"sim_b2b_{uuid.uuid4().hex[:14]}",
            "originator_conversation_id": f"sim_orig_{uuid.uuid4().hex[:12]}",
            "response_code": "0",
            "response_description": "Simulated B2B transfer accepted.",
            "transaction_id": f"SIM{uuid.uuid4().hex[:8].upper()}",
        }

    result_url, timeout_url = _resolve_b2b_callback_urls(cfg)
    shortcode = cfg["shortcode"]

    if dest == MpesaB2bTransfer.DestinationType.PHONE:
        payload = {
            "InitiatorName": cfg["initiator_name"],
            "SecurityCredential": cfg["security_credential"],
            "CommandID": "BusinessPayment",
            "Amount": amount_int,
            "PartyA": shortcode,
            "PartyB": party,
            "Remarks": note,
            "QueueTimeOutURL": timeout_url,
            "ResultURL": result_url,
            "Occasion": "Payment",
        }
        path = "/mpesa/b2c/v1/paymentrequest"
    else:
        command = (
            "BusinessBuyGoods"
            if dest == MpesaB2bTransfer.DestinationType.TILL
            else "BusinessPayBill"
        )
        payload = {
            "Initiator": cfg["initiator_name"],
            "SecurityCredential": cfg["security_credential"],
            "CommandID": command,
            "SenderIdentifierType": "4",
            "RecieverIdentifierType": "4",
            "Amount": amount_int,
            "PartyA": shortcode,
            "PartyB": party,
            "AccountReference": reference or "TRANSFER",
            "Remarks": note,
            "QueueTimeOutURL": timeout_url,
            "ResultURL": result_url,
        }
        path = "/mpesa/b2b/v1/paymentrequest"

    response = _post_daraja_json(cfg, path, payload)
    response_code = str(response.get("ResponseCode") or "")
    if response_code not in {"0", "00"}:
        raise MpesaError(
            response.get("ResponseDescription")
            or response.get("errorMessage")
            or "M-Pesa rejected the transfer request."
        )

    return {
        "simulated": False,
        "destination_type": dest,
        "party_b": party,
        "amount": amount_int,
        "account_reference": reference,
        "conversation_id": response.get("ConversationID") or "",
        "originator_conversation_id": response.get("OriginatorConversationID") or "",
        "response_code": response_code,
        "response_description": response.get("ResponseDescription") or "",
        "transaction_id": "",
    }


def request_account_balance() -> dict:
    """
    Ask Safaricom for the paybill / shortcode float balance (async).
    Updates FinanceSettings with the pending conversation id.
    """
    if not mpesa_b2b_configured():
        raise MpesaError(
            "Configure B2B credentials in Finance Settings before querying the paybill balance."
        )

    cfg = get_mpesa_b2b_runtime_config()
    from .models import FinanceSettings

    # Prefer dedicated balance URLs derived from result URL host when possible.
    result_url = (cfg.get("result_url") or "").strip()
    timeout_url = (cfg.get("timeout_url") or "").strip()
    try:
        parts = parse.urlparse(result_url)
        balance_result = f"{parts.scheme}://{parts.netloc}{MPESA_BALANCE_RESULT_PATH}"
        balance_timeout = f"{parts.scheme}://{parts.netloc}{MPESA_BALANCE_TIMEOUT_PATH}"
        if not is_valid_mpesa_callback_url(balance_result):
            balance_result = result_url
            balance_timeout = timeout_url
    except Exception:
        balance_result = result_url
        balance_timeout = timeout_url

    payload = {
        "Initiator": cfg["initiator_name"],
        "SecurityCredential": cfg["security_credential"],
        "CommandID": "AccountBalance",
        "PartyA": cfg["shortcode"],
        "IdentifierType": "4",
        "Remarks": "Paybill balance",
        "QueueTimeOutURL": balance_timeout,
        "ResultURL": balance_result,
    }
    response = _post_daraja_json(cfg, "/mpesa/accountbalance/v1/query", payload)
    response_code = str(response.get("ResponseCode") or "")
    if response_code not in {"0", "00"}:
        raise MpesaError(
            response.get("ResponseDescription")
            or "M-Pesa rejected the balance query."
        )

    conversation_id = response.get("ConversationID") or ""
    originator_id = response.get("OriginatorConversationID") or ""
    firm = FinanceSettings.get_solo()
    firm.mpesa_float_conversation_id = conversation_id or originator_id
    firm.save(update_fields=["mpesa_float_conversation_id", "updated_at"])

    return {
        "conversation_id": conversation_id,
        "originator_conversation_id": originator_id,
        "response_description": response.get("ResponseDescription") or "",
    }


def _parse_account_balance_string(raw: str) -> dict[str, Decimal]:
    """
    Parse Safaricom AccountBalance ResultParameter string, e.g.
    Working Account|KES|460.00&Utility Account|KES|...
    """
    mapping = {
        "working": Decimal("0.00"),
        "utility": Decimal("0.00"),
        "charges": Decimal("0.00"),
    }
    text = (raw or "").strip()
    if not text:
        return mapping

    for chunk in text.replace(";", "&").split("&"):
        parts = [p.strip() for p in chunk.split("|") if p.strip()]
        if len(parts) < 2:
            continue
        label = parts[0].lower()
        amount_raw = parts[-1].replace(",", "")
        try:
            amount = Decimal(amount_raw).quantize(Decimal("0.01"))
        except Exception:
            continue
        if "working" in label:
            mapping["working"] = amount
        elif "utility" in label:
            mapping["utility"] = amount
        elif "charge" in label:
            mapping["charges"] = amount
    return mapping


def process_account_balance_result(payload: dict) -> dict | None:
    """Apply an AccountBalance ResultURL callback onto FinanceSettings."""
    from .models import FinanceSettings

    result = (payload or {}).get("Result") or payload or {}
    result_code = str(result.get("ResultCode") if result.get("ResultCode") is not None else "")
    params = result.get("ResultParameters") or {}
    param_list = params.get("ResultParameter") or []
    if isinstance(param_list, dict):
        param_list = [param_list]

    balance_raw = ""
    for item in param_list:
        key = (item or {}).get("Key") or ""
        if key in {"AccountBalance", "BOCompletedTime"}:
            if key == "AccountBalance":
                balance_raw = str((item or {}).get("Value") or "")
                break

    parsed = _parse_account_balance_string(balance_raw)
    firm = FinanceSettings.get_solo()
    update_fields = [
        "mpesa_float_raw",
        "mpesa_float_checked_at",
        "updated_at",
    ]
    firm.mpesa_float_raw = json.dumps(payload)[:8000]
    firm.mpesa_float_checked_at = timezone.now()
    if result_code in {"0", "00"}:
        firm.mpesa_float_working = parsed["working"]
        firm.mpesa_float_utility = parsed["utility"]
        firm.mpesa_float_charges = parsed["charges"]
        update_fields.extend(
            ["mpesa_float_working", "mpesa_float_utility", "mpesa_float_charges"]
        )
    firm.save(update_fields=update_fields)
    return {
        "result_code": result_code,
        "working": str(parsed["working"]),
        "utility": str(parsed["utility"]),
        "charges": str(parsed["charges"]),
    }


def apply_paybill_float_debit(amount) -> None:
    """Reduce cached Safaricom float after a Paybill-funded payout."""
    from .models import FinanceSettings

    amount = Decimal(amount).quantize(Decimal("0.01"))
    if amount <= 0:
        return
    finance = FinanceSettings.get_solo()
    working = finance.mpesa_float_working
    utility = finance.mpesa_float_utility
    if working is None and utility is None:
        return
    remaining = amount
    update_fields = ["updated_at", "mpesa_float_checked_at"]
    finance.mpesa_float_checked_at = timezone.now()
    if working is not None:
        take = min(working, remaining)
        finance.mpesa_float_working = (working - take).quantize(Decimal("0.01"))
        remaining = (remaining - take).quantize(Decimal("0.01"))
        update_fields.append("mpesa_float_working")
    if remaining > 0 and utility is not None:
        take = min(utility, remaining)
        finance.mpesa_float_utility = (utility - take).quantize(Decimal("0.01"))
        update_fields.append("mpesa_float_utility")
    finance.save(update_fields=update_fields)


def _debit_company_account_for_transfer(transfer) -> None:
    """Debit the linked company ledger when a transfer completes."""
    from django.db import transaction
    from django.db.models import F

    from .models import CompanyExpenseAccount, CompanyExpensePayment

    if transfer.expense_payment_id or not transfer.company_account_id:
        return

    with transaction.atomic():
        locked = CompanyExpenseAccount.objects.select_for_update().get(
            pk=transfer.company_account_id
        )
        amount = Decimal(transfer.amount).quantize(Decimal("0.01"))
        if locked.balance < amount:
            raise MpesaError(
                f"Account “{locked.name}” has insufficient balance for this transfer."
            )
        CompanyExpenseAccount.objects.filter(pk=locked.pk).update(
            balance=F("balance") - amount
        )
        locked.refresh_from_db(fields=["balance"])
        payment = CompanyExpensePayment.objects.create(
            account=locked,
            expense_type=CompanyExpensePayment.ExpenseType.MPESA_TRANSFER,
            description=(
                f"M-Pesa transfer to {transfer.destination_display}"
                + (f" — {transfer.remarks}" if transfer.remarks else "")
            ),
            amount=amount,
            balance_after=locked.balance,
            created_by=transfer.created_by,
        )
        transfer.expense_payment = payment
        transfer.save(update_fields=["expense_payment"])


def process_b2b_result(payload: dict) -> dict | None:
    """Apply a B2B / B2C ResultURL callback onto MpesaB2bTransfer."""
    from .models import MpesaB2bTransfer

    result = (payload or {}).get("Result") or payload or {}
    originator_id = (result.get("OriginatorConversationID") or "").strip()
    conversation_id = (result.get("ConversationID") or "").strip()
    transfer = None
    if originator_id:
        transfer = (
            MpesaB2bTransfer.objects.filter(
                originator_conversation_id=originator_id
            )
            .order_by("-id")
            .first()
        )
    if transfer is None and conversation_id:
        transfer = (
            MpesaB2bTransfer.objects.filter(conversation_id=conversation_id)
            .order_by("-id")
            .first()
        )
    if transfer is None:
        logger.warning(
            "B2B result for unknown conversation originator=%s conversation=%s",
            originator_id,
            conversation_id,
        )
        return None

    if transfer.status == MpesaB2bTransfer.Status.COMPLETED:
        return {"status": transfer.status, "id": transfer.pk}

    result_code = str(result.get("ResultCode") if result.get("ResultCode") is not None else "")
    result_desc = (result.get("ResultDesc") or "")[:255]
    transaction_id = (result.get("TransactionID") or "")[:64]
    transfer.result_code = result_code
    transfer.result_desc = result_desc
    transfer.transaction_id = transaction_id or transfer.transaction_id
    transfer.raw_result = json.dumps(payload)[:8000]
    transfer.completed_at = timezone.now()

    if result_code in {"0", "00"}:
        transfer.status = MpesaB2bTransfer.Status.COMPLETED
        transfer.save(
            update_fields=[
                "status",
                "result_code",
                "result_desc",
                "transaction_id",
                "raw_result",
                "completed_at",
            ]
        )
        try:
            _debit_company_account_for_transfer(transfer)
            transfer.refresh_from_db()
            from .models import PettyCashExpenseRequest

            if transfer.expense_payment_id:
                PettyCashExpenseRequest.objects.filter(
                    mpesa_transfer=transfer,
                    expense_payment__isnull=True,
                ).update(expense_payment=transfer.expense_payment)
            elif not transfer.company_account_id:
                apply_paybill_float_debit(transfer.amount)
        except Exception:
            logger.exception("Failed to debit ledger for B2B transfer %s", transfer.pk)
    else:
        transfer.status = MpesaB2bTransfer.Status.FAILED
        transfer.save(
            update_fields=[
                "status",
                "result_code",
                "result_desc",
                "transaction_id",
                "raw_result",
                "completed_at",
            ]
        )

    return {"status": transfer.status, "id": transfer.pk}


def process_b2b_timeout(payload: dict) -> dict | None:
    """Mark a pending B2B transfer as timed out."""
    from .models import MpesaB2bTransfer

    result = (payload or {}).get("Result") or payload or {}
    originator_id = (result.get("OriginatorConversationID") or "").strip()
    conversation_id = (result.get("ConversationID") or "").strip()
    transfer = None
    if originator_id:
        transfer = (
            MpesaB2bTransfer.objects.filter(
                originator_conversation_id=originator_id
            )
            .order_by("-id")
            .first()
        )
    if transfer is None and conversation_id:
        transfer = (
            MpesaB2bTransfer.objects.filter(conversation_id=conversation_id)
            .order_by("-id")
            .first()
        )
    if transfer is None:
        return None
    if transfer.status in {
        MpesaB2bTransfer.Status.COMPLETED,
        MpesaB2bTransfer.Status.FAILED,
    }:
        return {"status": transfer.status, "id": transfer.pk}

    transfer.status = MpesaB2bTransfer.Status.TIMED_OUT
    transfer.result_desc = "Transfer timed out waiting for Safaricom."
    transfer.raw_result = json.dumps(payload)[:8000]
    transfer.completed_at = timezone.now()
    transfer.save(
        update_fields=["status", "result_desc", "raw_result", "completed_at"]
    )
    return {"status": transfer.status, "id": transfer.pk}
