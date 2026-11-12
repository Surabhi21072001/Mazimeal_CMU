"""The one place that decides whether a test may touch a database.

Every database test in this repository must go through here. The rule is simple and has no
override: the host must be this machine. Hosted databases (Supabase, anything with a public
name or address) are refused, however the DSN was supplied.
"""
from __future__ import annotations

LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
HOSTED_MARKERS = ("supabase", "amazonaws", "azure", "neon.tech", "render.com", "heroku", "pooler")


def is_local_host(host) -> bool:
    """True for loopback names/addresses and for a unix-socket directory (a path)."""
    if host is None or host == "":
        return True            # libpq's default: the local socket
    host = str(host).strip().lower()
    if any(marker in host for marker in HOSTED_MARKERS):
        return False
    return host in LOCAL_HOSTS or host.startswith("/")


def assert_local_host(host, what: str = "database") -> None:
    if not is_local_host(host):
        raise AssertionError("refusing to run against a non-local %s: %r" % (what, host))


def host_of_dsn(dsn: str):
    """The host named in a libpq DSN or URL, or None when it names none (default socket)."""
    from psycopg.conninfo import conninfo_to_dict

    parts = conninfo_to_dict(dsn)
    # A comma-separated host list is how libpq does failover; every entry must be local.
    return parts.get("host") or parts.get("hostaddr")


def assert_local_dsn(dsn: str) -> None:
    host = host_of_dsn(dsn)
    for one in (str(host).split(",") if host else [None]):
        assert_local_host(one, "DSN")
