"""Failed-login throttle for `POST /auth/login`.

The only limit on login was the global 120 per minute per IP, so one client could try passwords for
any account at that rate, and its failures got the API's own egress IP throttled by Supabase, which
blocked every login. Failed attempts are now counted per client IP and per email over a 15-minute
window. Fails open if Redis is unreachable, like the global limiter: a cache outage must not lock
everyone out.
"""

import hashlib

import structlog

log = structlog.get_logger(__name__)

WINDOW_SECONDS = 15 * 60
MAX_FAILURES_PER_IP = 20
MAX_FAILURES_PER_EMAIL = 5


def _keys(ip: str, email: str) -> tuple[str, str]:
    # The email is hashed so the key space never holds an address in clear text.
    digest = hashlib.sha256(email.strip().lower().encode()).hexdigest()[:32]
    return f"kairos:login_fail:ip:{ip}", f"kairos:login_fail:email:{digest}"


async def blocked(redis, ip: str, email: str) -> bool:
    """True when this IP or this account has failed too often in the window."""
    ip_key, email_key = _keys(ip, email)
    try:
        ip_count, email_count = await redis.mget(ip_key, email_key)
    except Exception as exc:  # noqa: BLE001 — fail open
        log.warning("login_throttle.redis_unavailable", error=str(exc))
        return False
    return int(ip_count or 0) >= MAX_FAILURES_PER_IP or int(email_count or 0) >= MAX_FAILURES_PER_EMAIL


async def record_failure(redis, ip: str, email: str) -> None:
    try:
        for key in _keys(ip, email):
            if await redis.incr(key) == 1:
                await redis.expire(key, WINDOW_SECONDS)
    except Exception as exc:  # noqa: BLE001 — fail open
        log.warning("login_throttle.redis_unavailable", error=str(exc))


async def clear_account(redis, ip: str, email: str) -> None:
    """A successful sign-in clears the account's count (not the IP's: one success must not reset a spray)."""
    try:
        await redis.delete(_keys(ip, email)[1])
    except Exception as exc:  # noqa: BLE001 — fail open
        log.warning("login_throttle.redis_unavailable", error=str(exc))
