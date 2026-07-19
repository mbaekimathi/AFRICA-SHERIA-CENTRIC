"""
One-time MySQL bootstrap on process start.

Local: may create the database if missing.
cPanel: connects to the DB you already created in MySQL Databases (no root).
"""

from __future__ import annotations

import os
import sys

_BOOTSTRAPPED = False

REQUIRED_TABLES = ("django_migrations", "accounts_employee")


def _should_skip_migrate_command() -> bool:
    skip = {
        "makemigrations",
        "migrate",
        "showmigrations",
        "sqlmigrate",
        "flush",
        "test",
        "collectstatic",
    }
    return any(arg in skip for arg in sys.argv)


def _is_autoreload_parent() -> bool:
    """True only for the Django StatReloader parent watcher process."""
    if "runserver" not in sys.argv:
        return False
    if "--noreload" in sys.argv:
        return False
    return os.environ.get("RUN_MAIN") != "true"


def _credentials_help() -> str:
    return (
        "\n"
        "MySQL login failed. On cPanel, create a database + user in "
        "MySQL Databases, then put them in .env:\n"
        "  DB_NAME=cpanel_dbname\n"
        "  DB_USER=cpanel_dbuser\n"
        "  DB_PASSWORD=your_password\n"
        "  DB_HOST=localhost\n"
        "Do not use root on shared hosting.\n"
    )


def ensure_mysql_database() -> str:
    from django.conf import settings

    db = settings.DATABASES["default"]
    name = str(db["NAME"])
    host = db.get("HOST") or "127.0.0.1"
    port = int(db.get("PORT") or 3306)
    user = db.get("USER") or "root"
    password = db.get("PASSWORD") or ""
    is_production = bool(getattr(settings, "IS_PRODUCTION", False))

    if is_production and user in {"", "root"} and not password:
        raise SystemExit(
            "Production MySQL is not configured.\n"
            "Set DB_NAME, DB_USER, DB_PASSWORD (and DB_HOST=localhost) in .env.\n"
            "Use the database/user from cPanel → MySQL Databases — not root."
        )

    import pymysql
    from pymysql.err import OperationalError

    # 1) Prefer connecting to the named DB (normal cPanel path).
    try:
        connection = pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=name,
            charset="utf8mb4",
            autocommit=True,
        )
        connection.close()
        return name
    except OperationalError as exc:
        errno = exc.args[0] if exc.args else None
        if errno == 1045:
            raise SystemExit(_credentials_help()) from exc
        if errno != 1049:
            # Unknown DB is the only case where we try CREATE below.
            raise SystemExit(
                f"Could not connect to MySQL database `{name}` "
                f"as `{user}`@{host}: {exc}\n"
                f"{_credentials_help()}"
            ) from exc

    # 2) Local/dev only: create missing database (cPanel users can't CREATE).
    if is_production:
        raise SystemExit(
            f"Database `{name}` does not exist.\n"
            "Create it in cPanel → MySQL Databases, assign your DB user to it, "
            "then set DB_NAME / DB_USER / DB_PASSWORD in .env."
        )

    try:
        connection = pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            charset="utf8mb4",
            autocommit=True,
        )
    except OperationalError as exc:
        if exc.args and exc.args[0] == 1045:
            raise SystemExit(_credentials_help()) from exc
        raise SystemExit(f"Could not connect to MySQL as `{user}`@{host}: {exc}") from exc

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{name}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
    finally:
        connection.close()
    return name


def tables_ready() -> bool:
    from django.db import connection

    try:
        connection.ensure_connection()
        with connection.cursor() as cursor:
            tables = set(connection.introspection.table_names(cursor))
        return all(table in tables for table in REQUIRED_TABLES)
    except Exception:
        return False


def has_pending_migrations() -> bool:
    """Fast check — True only when there are unapplied migration files."""
    try:
        from django.db import connection
        from django.db.migrations.executor import MigrationExecutor

        connection.ensure_connection()
        executor = MigrationExecutor(connection)
        return bool(executor.migration_plan(executor.loader.graph.leaf_nodes()))
    except Exception:
        # If we cannot inspect, force migrate so startup can self-heal.
        return True


def ensure_schema() -> None:
    """Create missing tables and apply any pending migrations."""
    from django.core.management import call_command

    needs_migrate = (not tables_ready()) or has_pending_migrations()
    if not needs_migrate:
        return
    call_command("migrate", interactive=False, verbosity=1)


def bootstrap_database(*, verbose: bool = False, from_runserver: bool = False) -> None:
    """Create MySQL DB (local) + apply migrations if needed. Once per process."""
    global _BOOTSTRAPPED
    if _BOOTSTRAPPED:
        return
    if not from_runserver and _is_autoreload_parent():
        return

    db_label = ensure_mysql_database()

    if not _should_skip_migrate_command():
        ensure_schema()

    _BOOTSTRAPPED = True

    if verbose or from_runserver:
        pending = has_pending_migrations()
        status = "ready" if tables_ready() and not pending else "needs attention"
        print(f"Database {status}: MySQL -> {db_label}")
