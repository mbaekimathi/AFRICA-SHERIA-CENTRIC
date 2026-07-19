"""
cPanel / Phusion Passenger WSGI entrypoint.

In cPanel → Setup Python App:
  - Application root: this project folder (contains manage.py)
  - Application startup file: passenger_wsgi.py
  - Application Entry point: application
"""

from __future__ import annotations

import os
import sys

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

os.chdir(PROJECT_DIR)
os.makedirs(os.path.join(PROJECT_DIR, "tmp"), exist_ok=True)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from config.wsgi import application  # noqa: E402
