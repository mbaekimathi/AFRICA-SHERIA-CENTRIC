"""
WSGI config for SHERIA-CENTRIC.
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_wsgi_application()

from config.db_bootstrap import bootstrap_database  # noqa: E402

bootstrap_database()
