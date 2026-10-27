"""Import attachments onto logged emails that predate attachment storage.

EmployeeCommunication rows only keep subject/body; the files travelled with the
real email on the mail server. This command matches each attachment-less log
row to its copy in the sender's Sent folder (or a colleague recipient's Inbox)
and saves the files onto the log record.

Run once after deploying attachment storage:

    python manage.py backfill_communication_attachments --dry-run
    python manage.py backfill_communication_attachments
"""

from collections import defaultdict
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Count, Q
from django.utils import timezone

from accounts.employee_communications import save_communication_attachments
from accounts.models import Employee, EmployeeCommunication, EmployeeMailbox
from accounts.work_mailbox import WorkMailbox, WorkMailboxError

_NO_SUBJECT = "(no subject)"


def _norm_subject(value: str) -> str:
    text = " ".join((value or "").split()).lower()
    return "" if text == _NO_SUBJECT else text


def _aware(value):
    if value is None:
        return None
    if timezone.is_naive(value):
        return timezone.make_aware(value)
    return value


class Command(BaseCommand):
    help = (
        "Copy attachments from mailbox Sent/Inbox copies onto logged "
        "employee emails that were sent before attachments were stored."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report matches without writing anything.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=500,
            help="How many recent messages to scan per mailbox folder.",
        )
        parser.add_argument(
            "--tolerance",
            type=int,
            default=15,
            help="Minutes apart the log timestamp and email date may be.",
        )
        parser.add_argument(
            "--employee-id",
            type=int,
            help="Only backfill emails sent by or to this employee.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        limit = max(1, options["limit"])
        tolerance = timedelta(minutes=max(1, options["tolerance"]))

        records = (
            EmployeeCommunication.objects.filter(
                channel=EmployeeCommunication.Channel.EMAIL
            )
            .annotate(attachment_count=Count("attachments"))
            .filter(attachment_count=0)
            .select_related("sender", "to_employee")
            .order_by("created_at")
        )
        if options["employee_id"]:
            records = records.filter(
                Q(sender_id=options["employee_id"])
                | Q(to_employee_id=options["employee_id"])
            )
        records = list(records)
        if not records:
            self.stdout.write("No logged emails are missing attachments.")
            return

        # One mailbox listing serves many records: (employee, mailbox, folder).
        sources = defaultdict(list)
        for record in records:
            for source in self._sources_for(record):
                sources[source].append(record)

        employees = {
            employee.pk: employee
            for employee in Employee.objects.filter(
                pk__in={key[0] for key in sources}
            ).prefetch_related("extra_mailboxes")
        }
        mailboxes = {
            mailbox.pk: mailbox
            for mailbox in EmployeeMailbox.objects.filter(
                pk__in={
                    int(key[1])
                    for key in sources
                    if isinstance(key[1], str) and key[1].isdigit()
                }
            )
        }

        done, matched, saved_files = set(), 0, 0
        for (employee_pk, mailbox_key, folder), group in sorted(
            sources.items(), key=lambda item: (str(item[0][0]), item[0][2])
        ):
            employee = employees.get(employee_pk)
            if employee is None:
                continue
            mailbox = mailboxes.get(int(mailbox_key)) if mailbox_key else None
            where = f"{employee.get_full_name()} · {folder}"
            try:
                client = WorkMailbox(employee, mailbox=mailbox)
                summaries = client.list_messages(folder, limit=limit)
            except WorkMailboxError as exc:
                self.stdout.write(self.style.WARNING(f"{where}: {exc}"))
                continue

            for record in group:
                if record.pk in done:
                    continue
                summary = self._best_match(record, summaries, folder, tolerance)
                if summary is None:
                    continue
                try:
                    detail = client.get_message(
                        folder, summary.uid, mark_seen=False
                    )
                except WorkMailboxError as exc:
                    self.stdout.write(
                        self.style.WARNING(
                            f"{where}: email #{record.pk} matched uid "
                            f"{summary.uid} but could not be read — {exc}"
                        )
                    )
                    continue
                if not detail.attachments:
                    continue
                matched += 1
                saved_files += len(detail.attachments)
                names = ", ".join(a.filename for a in detail.attachments)
                action = "would import" if dry_run else "imported"
                self.stdout.write(
                    self.style.SUCCESS(
                        f"{where}: email #{record.pk} “{record.subject}” — "
                        f"{action} {len(detail.attachments)} file(s): {names}"
                    )
                )
                if not dry_run:
                    save_communication_attachments(
                        record,
                        [
                            (a.filename, a.payload, a.content_type)
                            for a in detail.attachments
                        ],
                    )
                    done.add(record.pk)
                else:
                    done.add(record.pk)

        self.stdout.write(
            self.style.SUCCESS(
                f"{'[dry-run] ' if dry_run else ''}Matched {matched} email(s); "
                f"{saved_files} attachment file(s) "
                f"{'found' if dry_run else 'imported'}; "
                f"{len(records) - len(done)} email(s) had no match."
            )
        )

    def _sources_for(self, record) -> list[tuple]:
        """(employee_pk, mailbox_key, folder) lookups that may hold the email."""
        sources = []
        sender = record.sender
        from_identity = (record.from_identity or "").strip().lower()
        if sender is not None:
            mailbox_key = None
            if from_identity:
                for row in sender.mailbox_rows():
                    if row["email"] == from_identity and row["connected"]:
                        mailbox_key = row["key"]
                        break
            elif sender.mailbox_connected:
                mailbox_key = ""
            if mailbox_key is not None:
                sources.append((sender.pk, mailbox_key, "sent"))
        recipient = record.to_employee
        if recipient is not None and recipient.mailbox_connected:
            sources.append((recipient.pk, "", "inbox"))
        return sources

    @staticmethod
    def _best_match(record, summaries, folder, tolerance):
        subject = _norm_subject(record.subject)
        needle = (
            record.to_address if folder == "sent" else (record.from_identity or "")
        ).strip().lower()
        created = _aware(record.created_at)
        best, best_delta = None, None
        for summary in summaries:
            if _norm_subject(summary.subject) != subject:
                continue
            haystack = (
                summary.to_addrs if folder == "sent" else summary.from_addr
            ) or ""
            if needle and needle not in haystack.lower():
                continue
            sent_at = _aware(summary.sent_at)
            if sent_at is None or created is None:
                if best is None:
                    best = summary
                continue
            delta = abs(sent_at - created)
            if delta > tolerance:
                continue
            if best_delta is None or delta < best_delta:
                best, best_delta = summary, delta
        return best
