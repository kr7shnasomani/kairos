"""
Seed test users for Kairos development.
Creates the six role users (admin, engineer, field_worker, reliability, compliance, demo) in Supabase Auth.
Run inside the API container:
  docker exec kairos-backend-api python scripts/seed_users.py

Passwords come from the environment (`.env`, which is gitignored), one variable per role:
KAIROS_SEED_PASSWORD_ADMIN, _ENGINEER, _FIELD_WORKER, _RELIABILITY, _COMPLIANCE, _DEMO.
The demo user is the public one-click login: it works the showcase plant (`demo` role, site SITE_DEMO,
writes fenced to showcase rows), and its password is public by design (NEXT_PUBLIC_DEMO_PASSWORD on the frontend), so never reuse it for another account.
The script refuses to run if any is missing, so a password is never invented or committed.

role and site_id go in `app_metadata`, which only the service role can write. `user_metadata` is
editable by the user themselves, so it holds display data only (see dependencies.resolve_token).
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import structlog
from supabase import create_client

from api.config import settings

log = structlog.get_logger(__name__)

TEST_USERS = [
    {
        "email": "admin@kairos.local",
        "password_env": "KAIROS_SEED_PASSWORD_ADMIN",
        "app_metadata": {"role": "admin", "site_id": "SITE_001", "name": "Admin User"},
        "user_metadata": {"name": "Admin User"},
    },
    {
        "email": "engineer@kairos.local",
        "password_env": "KAIROS_SEED_PASSWORD_ENGINEER",
        "app_metadata": {"role": "engineer", "site_id": "SITE_001", "name": "Engineer User"},
        "user_metadata": {"name": "Engineer User"},
    },
    {
        "email": "field_worker@kairos.local",
        "password_env": "KAIROS_SEED_PASSWORD_FIELD_WORKER",
        "app_metadata": {"role": "field_worker", "site_id": "SITE_001", "name": "Field Worker"},
        "user_metadata": {"name": "Field Worker"},
    },
    # Reliability and compliance existed in OPA (infra/policies/kairos.rego) but had no seeded
    # user, so neither persona could be logged into — the two roles that actually demonstrate
    # governance were the two nobody could show. Reliability owns the one-way quarantine gate
    # (`promote_quarantine`, which engineers deliberately do NOT have); compliance is a read-only
    # auditor scoped to the compliance cockpit and audit trail.
    {
        "email": "reliability@kairos.local",
        "password_env": "KAIROS_SEED_PASSWORD_RELIABILITY",
        "app_metadata": {"role": "reliability", "site_id": "SITE_001", "name": "Reliability Engineer"},
        "user_metadata": {"name": "Reliability Engineer"},
    },
    {
        "email": "compliance@kairos.local",
        "password_env": "KAIROS_SEED_PASSWORD_COMPLIANCE",
        "app_metadata": {"role": "compliance", "site_id": "SITE_001", "name": "Compliance Auditor"},
        "user_metadata": {"name": "Compliance Auditor"},
    },
    # The login page's "Explore the live demo" button. It works the showcase plant (site SITE_DEMO): the
    # `demo` role reads every site but may write only to showcase rows (api/services/tenant.py).
    {
        "email": "demo@kairos.local",
        "password_env": "KAIROS_SEED_PASSWORD_DEMO",
        "app_metadata": {"role": "demo", "site_id": "SITE_DEMO", "name": "Demo Visitor"},
        "user_metadata": {"name": "Demo Visitor"},
    },
]


async def seed():
    # Fail before touching Supabase, and name every missing variable at once.
    missing = [u["password_env"] for u in TEST_USERS if not os.environ.get(u["password_env"])]
    if missing:
        log.error("seed_users.missing_passwords", variables=missing)
        sys.exit("Refusing to seed: set " + ", ".join(missing) + " in .env (see .env.example).")

    sb = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)

    existing = sb.auth.admin.list_users()
    existing_emails = {u.email for u in existing}

    for user in TEST_USERS:
        if user["email"] in existing_emails:
            log.info("seed_users.skip_existing", email=user["email"])
            continue
        result = sb.auth.admin.create_user({
            "email": user["email"],
            "password": os.environ[user["password_env"]],
            "app_metadata": user["app_metadata"],
            "user_metadata": user["user_metadata"],
            "email_confirm": True,
        })
        log.info("seed_users.created", email=result.user.email, id=str(result.user.id))

    log.info("seed_users.done", count=len(TEST_USERS))


if __name__ == "__main__":
    asyncio.run(seed())
