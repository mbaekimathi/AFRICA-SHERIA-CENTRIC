"""Read and send mail for an employee's firm work mailbox (IMAP + SMTP)."""

from __future__ import annotations

import email
import hashlib
import imaplib
import logging
import re
import smtplib
import ssl
from dataclasses import dataclass, field
from datetime import datetime
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.utils import formataddr, parsedate_to_datetime
from typing import Iterable

from django.core.cache import cache
from django.utils import timezone

from .mail_crypto import MailCryptoError

logger = logging.getLogger(__name__)

# A request blocked on the mail host is a Passenger worker not serving pages,
# so keep the ceiling well under how long a visitor will wait for the page.
IMAP_TIMEOUT_SECONDS = 8
SMTP_TIMEOUT_SECONDS = 30
OVERVIEW_CACHE_SECONDS = 60
DEFAULT_LIST_LIMIT = 40

FOLDER_ALIASES = {
    "inbox": ("INBOX",),
    "sent": ("Sent", "Sent Messages", "INBOX.Sent", "Sent Items"),
    "drafts": ("Drafts", "INBOX.Drafts"),
    "trash": ("Trash", "INBOX.Trash", "Deleted Messages", "Deleted Items"),
}


class WorkMailboxError(Exception):
    """Raised when the employee's mailbox cannot be reached or used."""


def _overview_cache_version(address: str) -> int:
    return cache.get(f"work-mailbox:version:{address}", 0)


def _bump_overview_cache_version(address: str) -> None:
    key = f"work-mailbox:version:{address}"
    cache.set(key, _overview_cache_version(address) + 1, None)


def _overview_cache_key(address: str, folder_key: str, limit: int, search: str) -> str:
    # Search terms are free text, so hash rather than risk an unusable key.
    raw = f"{_overview_cache_version(address)}|{address}|{folder_key}|{limit}|{search}"
    return f"work-mailbox:overview:{hashlib.sha1(raw.encode('utf-8')).hexdigest()}"


@dataclass
class MailAttachment:
    filename: str
    content_type: str
    payload: bytes
    size: int = 0
    part_index: int = 0


@dataclass
class MailSummary:
    uid: str
    subject: str
    from_addr: str
    to_addrs: str
    date_display: str
    snippet: str
    is_unread: bool
    has_attachments: bool
    sent_at: datetime | None = None

    @property
    def display_name(self) -> str:
        return display_name_for(self.from_addr)

    @property
    def initial(self) -> str:
        return initial_for(self.from_addr)

    @property
    def avatar_tone(self) -> int:
        return avatar_tone_for(self.from_addr)

    @property
    def short_date(self) -> str:
        return short_date_for(self.sent_at, self.date_display)


@dataclass
class MailDetail:
    uid: str
    subject: str
    from_addr: str
    to_addrs: str
    cc_addrs: str
    date_display: str
    body_text: str
    is_unread: bool
    attachments: list[MailAttachment] = field(default_factory=list)
    message_id: str = ""
    in_reply_to: str = ""

    @property
    def display_name(self) -> str:
        return display_name_for(self.from_addr)

    @property
    def sender_email(self) -> str:
        return _first_address(self.from_addr)

    @property
    def initial(self) -> str:
        return initial_for(self.from_addr)

    @property
    def avatar_tone(self) -> int:
        return avatar_tone_for(self.from_addr)


def mail_host_for_address(email_address: str) -> str:
    domain = (email_address or "").partition("@")[2].strip().lower()
    if not domain:
        raise WorkMailboxError("Work email address is incomplete.")
    return f"mail.{domain}"


def _decode_mime_header(value) -> str:
    if value is None:
        return ""
    try:
        return str(make_header(decode_header(str(value))))
    except Exception:
        return str(value)


def _first_address(value: str) -> str:
    text = _decode_mime_header(value).strip()
    match = re.search(r"<([^>]+)>", text)
    if match:
        return match.group(1).strip().lower()
    return text.lower()


def display_name_for(raw: str) -> str:
    """Friendly sender name: "Jane Doe" from `Jane Doe <jane@firm.com>`."""
    text = _decode_mime_header(raw).strip()
    if not text:
        return "Unknown sender"
    name = re.sub(r"<[^>]*>", "", text).strip().strip('"').strip("'").strip()
    if name:
        return name
    return text.partition("@")[0].lstrip("<") or text


def initial_for(raw: str) -> str:
    for char in display_name_for(raw):
        if char.isalnum():
            return char.upper()
    return "?"


def avatar_tone_for(raw: str) -> int:
    """Stable 0-6 palette slot so a sender keeps the same avatar colour."""
    key = _first_address(raw) or display_name_for(raw)
    return sum(ord(char) for char in key) % 7


def short_date_for(sent_at: datetime | None, fallback: str = "") -> str:
    """Gmail-style column date: time today, `12 Jul` this year, else `12/07/24`."""
    if sent_at is None:
        return (fallback or "").split(",")[0]
    local = timezone.localtime(sent_at) if timezone.is_aware(sent_at) else sent_at
    today = timezone.localdate()
    if local.date() == today:
        return local.strftime("%H:%M")
    if local.year == today.year:
        return local.strftime("%d %b")
    return local.strftime("%d/%m/%y")


def _parse_date(raw: str) -> datetime | None:
    try:
        return parsedate_to_datetime(raw)
    except Exception:
        return None


def _body_from_message(message: email.message.Message) -> str:
    if message.is_multipart():
        plain = ""
        html = ""
        for part in message.walk():
            disposition = str(part.get("Content-Disposition") or "").lower()
            if "attachment" in disposition:
                continue
            content_type = part.get_content_type()
            try:
                payload = part.get_payload(decode=True) or b""
                charset = part.get_content_charset() or "utf-8"
                text = payload.decode(charset, errors="replace")
            except Exception:
                continue
            if content_type == "text/plain" and not plain:
                plain = text
            elif content_type == "text/html" and not html:
                html = text
        if plain:
            return plain.strip()
        if html:
            return re.sub(r"<[^>]+>", " ", html)
        return ""
    try:
        payload = message.get_payload(decode=True) or b""
        charset = message.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace").strip()
    except Exception:
        return str(message.get_payload() or "").strip()


def _attachments_from_message(message: email.message.Message) -> list[MailAttachment]:
    attachments = []
    index = 0
    for part in message.walk():
        disposition = str(part.get("Content-Disposition") or "")
        filename = part.get_filename()
        if not filename and "attachment" not in disposition.lower():
            continue
        filename = _decode_mime_header(filename) or f"attachment-{index + 1}"
        payload = part.get_payload(decode=True) or b""
        attachments.append(
            MailAttachment(
                filename=filename,
                content_type=part.get_content_type() or "application/octet-stream",
                payload=payload,
                size=len(payload),
                part_index=index,
            )
        )
        index += 1
    return attachments


def _date_display(raw: str) -> str:
    try:
        dt = parsedate_to_datetime(raw)
        return dt.strftime("%d %b %Y, %H:%M")
    except Exception:
        return (raw or "")[:32]


class WorkMailbox:
    """IMAP/SMTP session for one employee's firm mailbox."""

    def __init__(self, employee):
        self.employee = employee
        self._folder_names: list[str] | None = None
        self.address = (employee.work_email or "").strip().lower()
        if not self.address:
            raise WorkMailboxError("Your account has no work email yet.")
        try:
            self.password = employee.get_work_mailbox_password()
        except MailCryptoError as exc:
            raise WorkMailboxError(
                "Connect your mailbox password to read and send mail here."
            ) from exc
        self.host = mail_host_for_address(self.address)

    def verify_credentials(self) -> None:
        with self._imap() as client:
            client.noop()

    def _imap(self):
        context = ssl.create_default_context()
        try:
            client = imaplib.IMAP4_SSL(
                self.host, 993, timeout=IMAP_TIMEOUT_SECONDS, ssl_context=context
            )
            client.login(self.address, self.password)
            return client
        except imaplib.IMAP4.error as exc:
            raise WorkMailboxError(
                "Mailbox login failed. Check the work email password."
            ) from exc
        except (OSError, TimeoutError, ssl.SSLError) as exc:
            raise WorkMailboxError(
                f"Could not reach {self.host}:993 — {exc}"
            ) from exc

    def _list_folder_names(self, client) -> list[str]:
        if self._folder_names is not None:
            return self._folder_names
        typ, data = client.list()
        names = []
        if typ == "OK" and data:
            for row in data:
                line = row.decode("utf-8", "replace") if isinstance(row, bytes) else str(row)
                # LIST (\HasNoChildren) "." "INBOX"
                match = re.search(r'"([^"]+)"\s*$', line) or re.search(r"\s(\S+)\s*$", line)
                if match:
                    names.append(match.group(1))
        self._folder_names = names
        return names

    def _resolve_folder(self, client, folder_key: str) -> str:
        key = (folder_key or "inbox").strip().lower()
        aliases = FOLDER_ALIASES.get(key, (folder_key,))
        names = self._list_folder_names(client)
        lower_map = {name.lower(): name for name in names}
        for alias in aliases:
            if alias.lower() in lower_map:
                return lower_map[alias.lower()]
            if alias in names:
                return alias
        if key == "inbox":
            return "INBOX"
        raise WorkMailboxError(f"Folder “{folder_key}” was not found on the mailbox.")

    def folder_overview(
        self,
        folder_key: str = "inbox",
        *,
        limit: int = DEFAULT_LIST_LIMIT,
        search: str = "",
        refresh: bool = False,
    ) -> dict:
        """One connection: the folder's messages plus unread counts for the rail.

        Held in the cache for a minute so repeat page views and back-navigation
        do not each pay for an IMAP login. Anything that changes the mailbox
        drops the entry, so sent mail and read receipts still appear at once.
        """
        cache_key = _overview_cache_key(self.address, folder_key, limit, search)
        if not refresh:
            cached = cache.get(cache_key)
            if cached is not None:
                return cached
        with self._imap() as client:
            messages = self._list_messages(
                client, folder_key, limit=limit, search=search
            )
            overview = {"messages": messages, "unread": self._unread_counts(client)}
        cache.set(cache_key, overview, OVERVIEW_CACHE_SECONDS)
        return overview

    def _invalidate_overviews(self) -> None:
        _bump_overview_cache_version(self.address)

    def _unread_counts(self, client) -> dict[str, int]:
        counts = {}
        for key in FOLDER_ALIASES:
            try:
                folder = self._resolve_folder(client, key)
                typ, data = client.status(f'"{folder}"', "(UNSEEN)")
            except (WorkMailboxError, imaplib.IMAP4.error, OSError):
                continue
            if typ != "OK" or not data:
                continue
            row = data[0]
            text = row.decode("utf-8", "replace") if isinstance(row, bytes) else str(row)
            match = re.search(r"UNSEEN\s+(\d+)", text)
            if match:
                counts[key] = int(match.group(1))
        return counts

    def list_messages(
        self,
        folder_key: str = "inbox",
        *,
        limit: int = DEFAULT_LIST_LIMIT,
        search: str = "",
    ) -> list[MailSummary]:
        with self._imap() as client:
            return self._list_messages(client, folder_key, limit=limit, search=search)

    def _list_messages(
        self,
        client,
        folder_key: str = "inbox",
        *,
        limit: int = DEFAULT_LIST_LIMIT,
        search: str = "",
    ) -> list[MailSummary]:
        folder = self._resolve_folder(client, folder_key)
        typ, _ = client.select(f'"{folder}"', readonly=True)
        if typ != "OK":
            typ, _ = client.select(folder, readonly=True)
        if typ != "OK":
            raise WorkMailboxError(f"Could not open folder {folder}.")
        query = (search or "").strip()
        if query:
            safe = query.replace('"', "").replace("\\", "")[:120]
            typ, data = client.uid(
                "search",
                None,
                "OR",
                "OR",
                "FROM",
                f'"{safe}"',
                "TO",
                f'"{safe}"',
                "SUBJECT",
                f'"{safe}"',
            )
            if typ != "OK":
                typ, data = client.uid("search", None, "TEXT", f'"{safe}"')
        else:
            typ, data = client.uid("search", None, "ALL")
        if typ != "OK" or not data or not data[0]:
            return []
        uids = data[0].split()
        uids = list(reversed(uids))[: max(1, int(limit))]
        summaries = []
        for uid in uids:
            typ, fetched = client.uid(
                "fetch",
                uid,
                "(FLAGS BODYSTRUCTURE "
                "BODY.PEEK[HEADER.FIELDS (SUBJECT FROM TO DATE)] "
                "BODY.PEEK[TEXT]<0.180>)",
            )
            if typ != "OK" or not fetched:
                continue
            meta_parts = []
            header_bytes = b""
            text_bytes = b""
            for item in fetched:
                if isinstance(item, tuple) and len(item) >= 2:
                    meta = item[0]
                    if isinstance(meta, bytes):
                        meta_parts.append(meta.decode("utf-8", "replace"))
                    payload = item[1]
                    if isinstance(payload, bytes):
                        if b"Subject:" in payload or b"From:" in payload:
                            header_bytes = payload
                        else:
                            text_bytes = payload
                elif isinstance(item, bytes):
                    meta_parts.append(item.decode("utf-8", "replace"))
            meta_text = " ".join(meta_parts)
            message = email.message_from_bytes(header_bytes or b"Subject: \n\n")
            subject = _decode_mime_header(message.get("Subject")) or "(no subject)"
            from_addr = _decode_mime_header(message.get("From"))
            to_addrs = _decode_mime_header(message.get("To"))
            raw_date = message.get("Date") or ""
            snippet = ""
            if text_bytes:
                snippet = text_bytes.decode("utf-8", "replace")
                snippet = re.sub(r"\s+", " ", snippet).strip()[:140]
            summaries.append(
                MailSummary(
                    uid=uid.decode("ascii") if isinstance(uid, bytes) else str(uid),
                    subject=subject,
                    from_addr=from_addr,
                    to_addrs=to_addrs,
                    date_display=_date_display(raw_date),
                    snippet=snippet,
                    is_unread="\\Seen" not in meta_text,
                    has_attachments='"attachment"' in meta_text.lower(),
                    sent_at=_parse_date(raw_date),
                )
            )
        return summaries

    def get_message(self, folder_key: str, uid: str) -> MailDetail:
        with self._imap() as client:
            folder = self._resolve_folder(client, folder_key)
            typ, _ = client.select(f'"{folder}"', readonly=False)
            if typ != "OK":
                typ, _ = client.select(folder, readonly=False)
            if typ != "OK":
                raise WorkMailboxError(f"Could not open folder {folder}.")
            typ, fetched = client.uid("fetch", str(uid), "(FLAGS BODY.PEEK[])")
            if typ != "OK" or not fetched:
                raise WorkMailboxError("Message was not found.")
            raw = b""
            flags = ""
            for item in fetched:
                if isinstance(item, tuple) and len(item) >= 2:
                    if isinstance(item[0], bytes):
                        flags = item[0].decode("utf-8", "replace")
                    if isinstance(item[1], bytes):
                        raw = item[1]
            if not raw:
                raise WorkMailboxError("Message body could not be loaded.")
            message = email.message_from_bytes(raw)
            was_unread = "\\Seen" not in flags
            # Mark seen
            try:
                client.uid("store", str(uid), "+FLAGS", "(\\Seen)")
            except Exception:
                pass
            if was_unread:
                self._invalidate_overviews()
            return MailDetail(
                uid=str(uid),
                subject=_decode_mime_header(message.get("Subject")) or "(no subject)",
                from_addr=_decode_mime_header(message.get("From")),
                to_addrs=_decode_mime_header(message.get("To")),
                cc_addrs=_decode_mime_header(message.get("Cc")),
                date_display=_date_display(message.get("Date") or ""),
                body_text=_body_from_message(message),
                is_unread="\\Seen" not in flags,
                attachments=_attachments_from_message(message),
                message_id=_decode_mime_header(message.get("Message-ID")),
                in_reply_to=_decode_mime_header(message.get("In-Reply-To")),
            )

    def get_attachment(
        self, folder_key: str, uid: str, part_index: int
    ) -> MailAttachment:
        detail = self.get_message(folder_key, uid)
        for attachment in detail.attachments:
            if attachment.part_index == int(part_index):
                return attachment
        raise WorkMailboxError("Attachment was not found.")

    def move_to_trash(self, folder_key: str, uid: str) -> None:
        with self._imap() as client:
            folder = self._resolve_folder(client, folder_key)
            typ, _ = client.select(f'"{folder}"', readonly=False)
            if typ != "OK":
                typ, _ = client.select(folder, readonly=False)
            trash = self._resolve_folder(client, "trash")
            try:
                client.uid("copy", str(uid), trash)
            except Exception:
                client.uid("copy", str(uid), f'"{trash}"')
            client.uid("store", str(uid), "+FLAGS", "(\\Deleted)")
            client.expunge()
        self._invalidate_overviews()

    def send_message(
        self,
        *,
        to_addrs: Iterable[str],
        subject: str,
        body: str,
        cc_addrs: Iterable[str] | None = None,
        bcc_addrs: Iterable[str] | None = None,
        attachments: list[tuple[str, bytes, str]] | None = None,
        in_reply_to: str = "",
        references: str = "",
        save_sent: bool = True,
    ) -> None:
        to_list = [a.strip() for a in to_addrs if (a or "").strip()]
        cc_list = [a.strip() for a in (cc_addrs or []) if (a or "").strip()]
        bcc_list = [a.strip() for a in (bcc_addrs or []) if (a or "").strip()]
        if not to_list:
            raise WorkMailboxError("Add at least one recipient.")
        subject_text = (subject or "").strip()
        body_text = (body or "").strip()
        if not subject_text:
            raise WorkMailboxError("Enter a subject.")
        if not body_text and not attachments:
            raise WorkMailboxError("Enter a message or attach a file.")

        message = EmailMessage()
        display = self.employee.get_full_name() or self.address
        message["From"] = formataddr((display, self.address))
        message["To"] = ", ".join(to_list)
        if cc_list:
            message["Cc"] = ", ".join(cc_list)
        message["Subject"] = subject_text
        if in_reply_to:
            message["In-Reply-To"] = in_reply_to
            message["References"] = references or in_reply_to
        message.set_content(body_text or " ")

        for filename, payload, content_type in attachments or []:
            maintype, _, subtype = (content_type or "application/octet-stream").partition(
                "/"
            )
            if not subtype:
                maintype, subtype = "application", "octet-stream"
            message.add_attachment(
                payload,
                maintype=maintype,
                subtype=subtype,
                filename=filename,
            )

        context = ssl.create_default_context()
        recipients = to_list + cc_list + bcc_list
        try:
            with smtplib.SMTP_SSL(
                self.host, 465, timeout=SMTP_TIMEOUT_SECONDS, context=context
            ) as server:
                server.login(self.address, self.password)
                server.send_message(
                    message, from_addr=self.address, to_addrs=recipients
                )
        except smtplib.SMTPAuthenticationError as exc:
            raise WorkMailboxError(
                "SMTP login failed. Reconnect your mailbox password."
            ) from exc
        except (smtplib.SMTPException, OSError, TimeoutError) as exc:
            raise WorkMailboxError(f"Email could not be sent: {exc}") from exc

        if save_sent:
            self._append_to_folder("sent", message.as_bytes())

    def save_draft(
        self,
        *,
        to_addrs: Iterable[str],
        subject: str,
        body: str,
        cc_addrs: Iterable[str] | None = None,
        attachments: list[tuple[str, bytes, str]] | None = None,
    ) -> None:
        to_list = [a.strip() for a in to_addrs if (a or "").strip()]
        cc_list = [a.strip() for a in (cc_addrs or []) if (a or "").strip()]
        message = EmailMessage()
        display = self.employee.get_full_name() or self.address
        message["From"] = formataddr((display, self.address))
        if to_list:
            message["To"] = ", ".join(to_list)
        if cc_list:
            message["Cc"] = ", ".join(cc_list)
        message["Subject"] = (subject or "").strip() or "(no subject)"
        message.set_content((body or "").strip() or " ")
        for filename, payload, content_type in attachments or []:
            maintype, _, subtype = (content_type or "application/octet-stream").partition(
                "/"
            )
            if not subtype:
                maintype, subtype = "application", "octet-stream"
            message.add_attachment(
                payload,
                maintype=maintype,
                subtype=subtype,
                filename=filename,
            )
        self._append_to_folder("drafts", message.as_bytes())

    def _append_to_folder(self, folder_key: str, raw: bytes) -> None:
        try:
            with self._imap() as client:
                folder = self._resolve_folder(client, folder_key)
                try:
                    client.append(folder, "\\Seen", None, raw)
                except Exception:
                    client.append(f'"{folder}"', "\\Seen", None, raw)
            self._invalidate_overviews()
        except WorkMailboxError:
            logger.warning(
                "Could not append message to %s for %s", folder_key, self.address
            )


def connect_mailbox(employee, password: str) -> None:
    """Validate password against IMAP and store it encrypted."""
    address = (employee.work_email or "").strip().lower()
    if not address:
        raise WorkMailboxError("Your account has no work email yet.")
    host = mail_host_for_address(address)
    context = ssl.create_default_context()
    try:
        with imaplib.IMAP4_SSL(
            host, 993, timeout=IMAP_TIMEOUT_SECONDS, ssl_context=context
        ) as client:
            client.login(address, password)
    except imaplib.IMAP4.error as exc:
        raise WorkMailboxError(
            "That password was rejected by the mail server."
        ) from exc
    except (OSError, TimeoutError, ssl.SSLError) as exc:
        raise WorkMailboxError(f"Could not reach {host}:993 — {exc}") from exc
    employee.set_work_mailbox_password(password)
