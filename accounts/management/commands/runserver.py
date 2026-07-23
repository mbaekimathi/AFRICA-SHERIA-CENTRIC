import atexit
import json
import socket
import subprocess
import time
import urllib.error
import urllib.request

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


def _find_ngrok() -> str | None:
    from shutil import which

    return which("ngrok")


class Command(StaticfilesRunserverCommand):
    """Starts the development server after ensuring DB/tables exist."""

    help = (
        "Starts the development server after ensuring DB/tables exist. "
        "Binds to 0.0.0.0 by default (localhost + LAN). "
        "Pass --share for a public ngrok URL you can send to anyone."
    )
    # Listen on all interfaces so phones/tablets on the same Wi-Fi can connect.
    default_addr = "0.0.0.0"

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument(
            "--share",
            action="store_true",
            help=(
                "Start an ngrok tunnel and print a public HTTPS URL you can share "
                "(works outside your Wi-Fi)."
            ),
        )

    def inner_run(self, *args, **options):
        bootstrap_database(verbose=True, from_runserver=True)
        self._share_proc = None
        self._print_access_links(share=bool(options.get("share")))
        try:
            super().inner_run(*args, **options)
        finally:
            self._stop_share_tunnel()

    def _print_access_links(self, *, share: bool) -> None:
        port = str(getattr(self, "port", "8000"))
        addr = getattr(self, "addr", self.default_addr)

        lines = [
            "",
            "Open the app:",
            f"  Local:   http://127.0.0.1:{port}/",
            f"  Local:   http://localhost:{port}/",
        ]

        if addr in ("0.0.0.0", "::", "[::]"):
            lan = _lan_ip()
            if lan:
                lines.append(f"  Network: http://{lan}:{port}/")
                lines.append(
                    "           (same Wi-Fi — phone/tablet/other PC; "
                    "allow Python in Windows Firewall if prompted)"
                )
            else:
                lines.append(
                    f"  Network: bound to all interfaces, but LAN IP unknown. "
                    f"Try http://<your-pc-ip>:{port}/"
                )
        else:
            lines.append(
                f"  Network: listening only on {addr}:{port}. "
                "Use `py manage.py runserver 0.0.0.0:8000` for other devices."
            )

        if share:
            public = self._start_share_tunnel(port)
            if public:
                lines.append(f"  Public:  {public}")
                lines.append(
                    "           (share this link with anyone — ngrok tunnel)"
                )
            else:
                lines.append(
                    "  Public:  could not start ngrok. "
                    "Install/configure ngrok, or omit --share and use Network."
                )
        else:
            lines.append(
                "  Public:  (off) restart with "
                "`py manage.py runserver --share` for a shareable internet link"
            )

        lines.append("")
        # print() so autoreload child output shows reliably in the terminal
        print("\n".join(lines), flush=True)

    def _start_share_tunnel(self, port: str) -> str | None:
        # Reuse an already-running ngrok agent if it exposes a public URL.
        existing = self._fetch_ngrok_url()
        if existing:
            return existing

        ngrok = _find_ngrok()
        if not ngrok:
            self.stderr.write(
                self.style.ERROR(
                    "ngrok not found on PATH. Install from https://ngrok.com/download "
                    "then run: ngrok config add-authtoken <token>"
                )
            )
            return None

        try:
            self._share_proc = subprocess.Popen(
                [ngrok, "http", port, "--log=stdout", "--log-format=logfmt"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as exc:
            self.stderr.write(self.style.ERROR(f"Failed to start ngrok: {exc}"))
            self._share_proc = None
            return None

        atexit.register(self._stop_share_tunnel)

        public = self._wait_for_ngrok_url(timeout=20)
        if not public:
            self._stop_share_tunnel()
            self.stderr.write(
                self.style.ERROR(
                    "ngrok started but no public URL appeared. "
                    "Check `ngrok config check` and your authtoken."
                )
            )
            return None
        return public

    def _fetch_ngrok_url(self) -> str | None:
        try:
            with urllib.request.urlopen(
                "http://127.0.0.1:4040/api/tunnels", timeout=1
            ) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
            return None
        https = None
        any_url = None
        for tunnel in data.get("tunnels") or []:
            url = (tunnel.get("public_url") or "").strip()
            if not url:
                continue
            if url.startswith("https://"):
                https = url
                break
            any_url = any_url or url
        return https or any_url

    def _wait_for_ngrok_url(self, *, timeout: float) -> str | None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._share_proc and self._share_proc.poll() is not None:
                return None
            public = self._fetch_ngrok_url()
            if public:
                return public
            time.sleep(0.4)
        return None

    def _stop_share_tunnel(self) -> None:
        proc = getattr(self, "_share_proc", None)
        if not proc:
            return
        self._share_proc = None
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
