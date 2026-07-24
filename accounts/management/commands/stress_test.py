"""
Concurrency stress test for live-poll and workspace endpoints.

Simulates many authenticated employee sessions hitting the high-frequency
APIs that dominate production load (notifications + account status).

Default mode is in-process (Django test client) so results measure view/DB
cost without depending on runserver. Pass --http to hit a live server.

Usage:
  python manage.py stress_test
  python manage.py stress_test --sessions 40 --requests 20 --workers 40
  python manage.py stress_test --http --base-url http://127.0.0.1:8000
"""

from __future__ import annotations

import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.contrib.auth import HASH_SESSION_KEY, SESSION_KEY, BACKEND_SESSION_KEY
from django.contrib.auth.hashers import make_password
from django.contrib.sessions.backends.db import SessionStore
from django.core.management.base import BaseCommand
from django.db import close_old_connections, connection
from django.test import Client

from accounts.models import Employee


class Command(BaseCommand):
    help = "Stress-test notification/status endpoints under many concurrent sessions."

    def add_arguments(self, parser):
        parser.add_argument(
            "--sessions",
            type=int,
            default=25,
            help="Number of concurrent authenticated sessions to simulate.",
        )
        parser.add_argument(
            "--requests",
            type=int,
            default=12,
            help="Requests per session (split across endpoints).",
        )
        parser.add_argument(
            "--workers",
            type=int,
            default=12,
            help="Thread pool size for concurrent calls.",
        )
        parser.add_argument(
            "--http",
            action="store_true",
            help="Hit a live HTTP server instead of the in-process test client.",
        )
        parser.add_argument(
            "--base-url",
            default="http://127.0.0.1:8000",
            help="Used with --http.",
        )
        parser.add_argument(
            "--keep-users",
            action="store_true",
            help="Do not delete temporary stress-test employees afterwards.",
        )

    def handle(self, *args, **options):
        sessions = max(1, options["sessions"])
        per_session = max(1, options["requests"])
        workers = max(1, options["workers"])
        use_http = options["http"]
        base_url = options["base_url"].rstrip("/")
        keep_users = options["keep_users"]

        mode = f"HTTP {base_url}" if use_http else "in-process"
        self._log(
            f"Preparing {sessions} sessions ({mode}, "
            f"{per_session} req/session, {workers} workers)..."
        )

        employees = self._ensure_employees(sessions)
        self._log(f"Ready: {len(employees)} employees")

        paths = (
            "/api/workspace/notifications/",
            "/employee/api/status/",
        )

        # Pre-create Django sessions once — mirrors many open tabs, avoids
        # re-login (and last_login writes) on every request.
        session_keys = [self._session_cookie(emp) for emp in employees]
        jobs = [
            (session_key, paths[i % len(paths)])
            for session_key in session_keys
            for i in range(per_session)
        ]

        self._log(f"Firing {len(jobs)} concurrent requests...")
        started = time.perf_counter()
        results = []
        with ThreadPoolExecutor(max_workers=workers) as pool:
            if use_http:
                futures = [
                    pool.submit(self._fetch_http, base_url, path, cookie)
                    for cookie, path in jobs
                ]
            else:
                futures = [
                    pool.submit(self._fetch_client, session_key, path)
                    for session_key, path in jobs
                ]
            for future in as_completed(futures):
                results.append(future.result())
        elapsed = time.perf_counter() - started

        if not keep_users:
            deleted, _ = Employee.objects.filter(
                personal_email__startswith="stress+",
                personal_email__endswith="@sheria.stress",
            ).delete()
            self._log(f"Cleaned up stress employees ({deleted} rows touched)")

        self._report(results, elapsed)

    def _log(self, message: str) -> None:
        self.stdout.write(message)
        try:
            self.stdout.flush()
        except Exception:
            pass

    def _ensure_employees(self, count: int) -> list[Employee]:
        close_old_connections()
        # Creating employees normally triggers Google Drive folder setup — skip that
        # for synthetic stress accounts so setup stays local and fast.
        from django.db.models.signals import post_save

        from accounts.signals import ensure_employee_drive_folders_on_save

        post_save.disconnect(ensure_employee_drive_folders_on_save, sender=Employee)
        hashed = make_password("stress-test-pass")
        employees: list[Employee] = []
        try:
            for i in range(count):
                login_code = f"{900000 + i:06d}"
                email = f"stress+{login_code}@sheria.stress"
                phone = f"+25471{i:07d}"
                employee, created = Employee.objects.get_or_create(
                    login_code=login_code,
                    defaults={
                        "personal_email": email,
                        "first_name": "Stress",
                        "last_name": f"User{i:03d}",
                        "personal_phone": phone,
                        "role": Employee.Role.EMPLOYEE,
                        "status": Employee.Status.ACTIVE,
                        "id_type": Employee.IdType.CITIZEN,
                        "id_country": "KE",
                        "identification_number": f"STRESS{login_code}",
                        "is_active": True,
                        "password": hashed,
                    },
                )
                if not created:
                    employee.status = Employee.Status.ACTIVE
                    employee.is_active = True
                    employee.personal_email = email
                    employee.save(
                        update_fields=["status", "is_active", "personal_email"]
                    )
                employees.append(employee)
                if (i + 1) % 10 == 0:
                    self._log(f"  prepared {i + 1}/{count}")
        finally:
            post_save.connect(ensure_employee_drive_folders_on_save, sender=Employee)
        return employees

    def _session_cookie(self, employee: Employee) -> str:
        close_old_connections()
        store = SessionStore()
        store[SESSION_KEY] = str(employee.pk)
        store[BACKEND_SESSION_KEY] = "django.contrib.auth.backends.ModelBackend"
        store[HASH_SESSION_KEY] = employee.get_session_auth_hash()
        store.save()
        return store.session_key

    def _fetch_client(self, session_key: str, path: str) -> dict:
        close_old_connections()
        started = time.perf_counter()
        status = 0
        error = ""
        bytes_out = 0
        try:
            client = Client()
            client.cookies["sessionid"] = session_key
            response = client.get(path, HTTP_ACCEPT="application/json")
            status = response.status_code
            content = getattr(response, "content", b"") or b""
            bytes_out = len(content)
        except Exception as exc:  # noqa: BLE001
            status = 0
            error = str(exc)
        finally:
            try:
                connection.close()
            except Exception:
                pass
        duration_ms = (time.perf_counter() - started) * 1000
        return {
            "path": path,
            "status": status,
            "duration_ms": duration_ms,
            "bytes": bytes_out,
            "error": error,
        }

    def _fetch_http(self, base_url: str, path: str, session_key: str) -> dict:
        close_old_connections()
        url = f"{base_url}{path}"
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "Cookie": f"sessionid={session_key}",
                "User-Agent": "SheriaStressTest/1.0",
            },
        )
        started = time.perf_counter()
        status = 0
        error = ""
        bytes_out = 0
        try:
            with urlopen(request, timeout=20) as response:
                body = response.read()
                status = getattr(response, "status", 200) or 200
                bytes_out = len(body)
        except HTTPError as exc:
            status = exc.code
            error = str(exc.reason)
            try:
                bytes_out = len(exc.read() or b"")
            except Exception:
                bytes_out = 0
        except URLError as exc:
            status = 0
            error = str(exc.reason)
        except Exception as exc:  # noqa: BLE001
            status = 0
            error = str(exc)
        duration_ms = (time.perf_counter() - started) * 1000
        return {
            "path": path,
            "status": status,
            "duration_ms": duration_ms,
            "bytes": bytes_out,
            "error": error,
        }

    def _report(self, results: list[dict], elapsed: float) -> None:
        ok = [r for r in results if 200 <= r["status"] < 400]
        fail = [r for r in results if r not in ok]
        durations = sorted(r["duration_ms"] for r in results)

        def pct(p: float) -> float:
            if not durations:
                return 0.0
            idx = min(
                len(durations) - 1,
                max(0, int(round((p / 100) * (len(durations) - 1)))),
            )
            return durations[idx]

        self._log("")
        self._log("=== Stress test results ===")
        self._log(f"Total requests : {len(results)}")
        self._log(f"Successful     : {len(ok)}")
        self._log(f"Failed         : {len(fail)}")
        self._log(f"Wall time      : {elapsed:.2f}s")
        self._log(f"Throughput     : {len(results) / max(elapsed, 0.001):.1f} req/s")
        if durations:
            self._log(
                f"Latency ms     : "
                f"avg={statistics.mean(durations):.0f}  "
                f"p50={pct(50):.0f}  "
                f"p95={pct(95):.0f}  "
                f"p99={pct(99):.0f}  "
                f"max={durations[-1]:.0f}"
            )

        by_path: dict[str, list[float]] = {}
        for row in results:
            by_path.setdefault(row["path"], []).append(row["duration_ms"])
        for path, values in sorted(by_path.items()):
            self._log(
                f"  {path}: n={len(values)} avg={statistics.mean(values):.0f}ms "
                f"max={max(values):.0f}ms"
            )

        if fail:
            self._log("Sample failures:")
            for row in fail[:5]:
                self._log(
                    f"  {row['status']} {row['path']} - {row['error'] or 'error'}"
                )
