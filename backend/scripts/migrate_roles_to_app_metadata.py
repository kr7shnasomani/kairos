"""
Copy `role`, `site_id` and the display `name` from `user_metadata` to `app_metadata` for existing Supabase Auth users.

Why: `dependencies.resolve_token` now reads authorization data from `app_metadata` only, because
`user_metadata` is writable by the user themselves (2026-09-30 security review, H1). A user that has the role
only in `user_metadata` resolves as `field_worker` with no site until this has run.

Additive and safe to run BEFORE deploying that code: `user_metadata` is left untouched, and a key
already present in `app_metadata` is never overwritten.

DRY RUN BY DEFAULT. Nothing is written without `--apply`. This writes to the cloud Supabase Auth
project, so read the dry-run output first: anyone who edited their own `user_metadata` to a
higher role shows up as a role you do not expect, and `--apply` would bless it.

  docker exec kairos-backend-api python scripts/migrate_roles_to_app_metadata.py            # dry run
  docker exec kairos-backend-api python scripts/migrate_roles_to_app_metadata.py --apply    # writes

`name` is copied too: `services/identity.display_name` reads it from `app_metadata` now, because a
name in `user_metadata` is user-editable and shows on PTW sign-offs.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import structlog
from supabase import create_client

from api.config import settings

log = structlog.get_logger(__name__)

KEYS = ("role", "site_id", "name")
KNOWN_ROLES = frozenset({"admin", "engineer", "field_worker", "reliability", "compliance", "demo"})
PAGE_SIZE = 200


def plan_for(user) -> dict | None:
    """The merged `app_metadata` to write for this user, or None when there is nothing to copy.

    A role outside KNOWN_ROLES is not copied: it matches no policy anyway, and copying an
    unrecognised value into the trusted field would only legitimise it.
    """
    app = dict(user.app_metadata or {})
    src = user.user_metadata or {}
    add = {k: src[k] for k in KEYS if src.get(k) and k not in app}
    if add.get("role") not in (None, *KNOWN_ROLES):
        log.warning("migrate_roles.unknown_role_skipped", email=user.email, role=add.pop("role"))
    if not add:
        return None
    return {**app, **add}


def all_users(sb) -> list:
    users, page = [], 1
    while True:
        batch = sb.auth.admin.list_users(page=page, per_page=PAGE_SIZE)
        users.extend(batch)
        if len(batch) < PAGE_SIZE:
            return users
        page += 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--apply", action="store_true", help="write the changes (default is a dry run)")
    apply = parser.parse_args(argv).apply

    sb = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
    changed = 0
    for user in all_users(sb):
        merged = plan_for(user)
        if merged is None:
            log.info("migrate_roles.nothing_to_do", email=user.email)
            continue
        changed += 1
        log.info(
            "migrate_roles.apply" if apply else "migrate_roles.would_apply",
            email=user.email,
            id=str(user.id),
            role=merged.get("role"),
            site_id=merged.get("site_id"),
            name=merged.get("name"),
        )
        if apply:
            sb.auth.admin.update_user_by_id(str(user.id), {"app_metadata": merged})

    log.info("migrate_roles.done", users_changed=changed, dry_run=not apply)
    if not apply and changed:
        log.info("migrate_roles.dry_run_notice", hint="re-run with --apply to write")
    return 0


if __name__ == "__main__":
    sys.exit(main())
