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

from accounts.communication_backfill import (
    DEFAULT_TOLERANCE_MINUTES,
    best_match,
    candidate_sources,
)
from accounts.employee_communications import save_communication_attachments
from accounts.models import EmployeeCommunication
from accounts.work_mailbox import WorkMailbox, WorkMailboxError


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
            default=DEFAULT_TOLERANCE_MINUTES,
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

        # One mailbox listing serves many records.
        groups = defaultdict(list)
        for record in records:
            for employee, mailbox, folder in candidate_sources(record):
                groups[(employee, mailbox, folder)].append(record)

        done, matched, saved_files = set(), 0, 0
        for (employee, mailbox, folder), group in sorted(
            groups.items(), key=lambda item: (item[0][0].pk, item[0][2])
        ):
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
                summary = best_match(record, summaries, folder, tolerance)
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

        self.stdout.write(
            self.style.SUCCESS(
                f"{'[dry-run] ' if dry_run else ''}Matched {matched} email(s); "
                f"{saved_files} attachment file(s) "
                f"{'found' if dry_run else 'imported'}; "
                f"{len(records) - len(done)} email(s) had no match."
            )
        )
