"""Kairos backend API package."""

# Every process that imports `api` — the API, Celery and Temporal workers, scripts — gets Supabase
# REST reads that survive a dropped pooled connection. See `api/supabase_http.py`.
from api.supabase_http import install as _install_supabase_retry

_install_supabase_retry()
