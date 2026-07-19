"""
ASGI config for SHERIA-CENTRIC.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_asgi_application()

from config.db_bootstrap import bootstrap_database  # noqa: E402

bootstrap_database()
