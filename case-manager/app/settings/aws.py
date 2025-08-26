# -*- coding: utf-8 -*-
"""AWS Django settings

Usage:
- export DJANGO_SETTINGS_MODULE=app.settings.aws
"""
import copy
import logging

from .base import *

logger = logging.getLogger(__name__)

DEBUG = False
PG_HOST = os.environ.get("PG_HOST")
PG_USER = os.environ.get("PG_USER")
PG_DB_NAME = os.environ.get("PG_DB_NAME")


DATABASES = {
    "default": {
        "HOST": PG_HOST,
        "USER": PG_USER,
        "NAME": PG_DB_NAME,
        "ENGINE": 'django_iam_dbauth.aws.postgresql',
        "OPTIONS": {
            "use_iam_auth": True,
            "sslmode": "require",
            "resolve_cname_enabled": False,
        }
    }
}

CORS_ORIGIN_ALLOW_ALL = False
CORS_ALLOW_CREDENTIALS = False

CORS_ALLOWED_ORIGINS = [
    "https://orcaui.dev.umccr.org",
    "https://orcaui.stg.umccr.org",
    "https://orcaui.prod.umccr.org",
    "https://orcaui.umccr.org",
]

CSRF_TRUSTED_ORIGINS = copy.deepcopy(CORS_ALLOWED_ORIGINS)
