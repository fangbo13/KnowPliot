from .base import *  # noqa: F401,F403
import os

# Production settings
DEBUG = False

# Security
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# Allowed hosts from env
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",")

# CORS - production origins only
CORS_ALLOW_ALL_ORIGINS = False
