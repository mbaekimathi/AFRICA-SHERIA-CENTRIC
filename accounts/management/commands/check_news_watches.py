from django.core.management.base import BaseCommand

from accounts.news_watch import run_due_news_watches


class Command(BaseCommand):
    help = "Check due saved news searches and publisher watches."

    def handle(self, *args, **options):
        checked, updates = run_due_news_watches()
        self.stdout.write(
            self.style.SUCCESS(
                f"Checked {checked} news watch(es); found {updates} update(s)."
            )
        )
