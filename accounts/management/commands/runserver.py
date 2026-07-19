import socket

from django.contrib.staticfiles.management.commands.runserver import (
    Command as StaticfilesRunserverCommand,
)

from config.db_bootstrap import bootstrap_database


def _lan_ip() -> str | None:
    """Best-effort LAN address other devices can use to reach this machine."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        return None


class Command(StaticfilesRunserverCommand):
    """Starts the development server after ensuring DB/tables exist."""

    help = (
        "Starts the development server after ensuring DB/tables exist. "
        "Binds to 0.0.0.0 by default so other devices on your network can open the printed Network link."
    )
    # Listen on all interfaces so phones/tablets on the same Wi‑Fi can connect.
    default_addr = "0.0.0.0"

    def inner_run(self, *args, **options):
        bootstrap_database(verbose=True, from_runserver=True)
        self._print_network_link()
        super().inner_run(*args, **options)

    def _print_network_link(self) -> None:
        port = getattr(self, "port", "8000")
        addr = getattr(self, "addr", self.default_addr)
        if addr in ("0.0.0.0", "::", "[::]"):
            lan = _lan_ip()
            if lan:
                url = f"http://{lan}:{port}/"
                self.stdout.write(self.style.SUCCESS(f"Network (other devices): {url}"))
                self.stdout.write(
                    "Open that link on another device on the same Wi‑Fi "
                    "(allow Python through Windows Firewall if prompted)."
                )
            else:
                self.stdout.write(
                    self.style.WARNING(
                        "Bound to all interfaces, but could not detect a LAN IP. "
                        f"Try http://<your-pc-ip>:{port}/ from another device."
                    )
                )
        else:
            self.stdout.write(
                self.style.WARNING(
                    f"Listening only on {addr}:{port}. "
                    "Use `py manage.py runserver 0.0.0.0:8000` for other devices."
                )
            )
