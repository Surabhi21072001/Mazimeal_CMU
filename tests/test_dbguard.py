#!/usr/bin/env python3
"""The guard that keeps database tests on this machine. Needs no database.

    python3 -m unittest tests.test_dbguard -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dbguard  # noqa: E402

try:
    import psycopg  # noqa: F401
    HAVE_PSYCOPG = True
except ImportError:  # pragma: no cover
    HAVE_PSYCOPG = False


class Hosts(unittest.TestCase):
    def test_loopback_and_sockets_are_local(self):
        for h in ("127.0.0.1", "localhost", "::1", "LOCALHOST", "/tmp", "/var/run/postgresql", None, ""):
            self.assertTrue(dbguard.is_local_host(h), h)

    def test_everything_else_is_refused(self):
        for h in ("db.abcdefgh.supabase.co", "aws-0-us-east-1.pooler.supabase.com", "10.0.0.5", "192.168.1.20",
                  "prod.example.com", "mydb.rds.amazonaws.com", "ep-cool-1.us-east-2.aws.neon.tech", "0.0.0.0",
                  "127.0.0.1.evil.com", "localhost.example.com"):
            self.assertFalse(dbguard.is_local_host(h), h)

    def test_hosted_marker_wins_even_if_it_looks_like_a_path(self):
        self.assertFalse(dbguard.is_local_host("/supabase/db"))

    def test_assert_local_host_raises_for_remote(self):
        with self.assertRaises(AssertionError) as ctx:
            dbguard.assert_local_host("db.x.supabase.co")
        self.assertIn("non-local", str(ctx.exception))
        dbguard.assert_local_host("127.0.0.1")  # does not raise


@unittest.skipUnless(HAVE_PSYCOPG, "psycopg not installed")
class Dsns(unittest.TestCase):
    def test_local_dsns_pass(self):
        for dsn in ("postgresql://audit@127.0.0.1:54329/mazi_audit", "postgresql://u:p@localhost/db",
                    "host=127.0.0.1 port=5432 dbname=x", "postgresql:///x?host=/tmp", "dbname=x"):
            dbguard.assert_local_dsn(dsn)

    def test_remote_dsns_are_refused(self):
        for dsn in ("postgresql://postgres:secret@db.abc.supabase.co:5432/postgres",
                    "host=aws-0-eu.pooler.supabase.com port=6543 dbname=postgres",
                    "postgresql://u@10.1.2.3/db", "postgresql://u@prod.internal.example.com/db"):
            with self.assertRaises(AssertionError, msg=dsn):
                dbguard.assert_local_dsn(dsn)

    def test_one_remote_host_in_a_failover_list_is_enough_to_refuse(self):
        with self.assertRaises(AssertionError):
            dbguard.assert_local_dsn("host=127.0.0.1,db.x.supabase.co dbname=x")

    def test_host_of_dsn(self):
        self.assertEqual(dbguard.host_of_dsn("postgresql://u@127.0.0.1:1/db"), "127.0.0.1")
        self.assertIsNone(dbguard.host_of_dsn("dbname=x"))


if __name__ == "__main__":
    unittest.main()
