from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"
    verbose_name = "Accounts"

    def ready(self):
        from . import signals  # noqa: F401
        from .workspace import validate_permission_registry

        missing = validate_permission_registry()
        if missing:
            import logging

            logging.getLogger(__name__).warning(
                "Permission registry missing %d activities: %s",
                len(missing),
                ", ".join(sorted(missing)[:20])
                + ("…" if len(missing) > 20 else ""),
            )
