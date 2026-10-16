#!/usr/bin/env python
"""Container entrypoint: wait for Postgres, migrate, then exec the service command."""

from __future__ import annotations

import os
import subprocess
import sys
import time


def wait_for_db(timeout_s: int = 60) -> None:
    import dj_database_url
    import psycopg2

    url = os.environ.get(
        "DATABASE_URL",
        "postgres://goldcorp:goldcorp@db:5432/goldcorp",
    )
    cfg = dj_database_url.parse(url)
    deadline = time.time() + timeout_s
    attempt = 0
    while time.time() < deadline:
        attempt += 1
        try:
            conn = psycopg2.connect(
                dbname=cfg["NAME"],
                user=cfg["USER"],
                password=cfg["PASSWORD"],
                host=cfg["HOST"],
                port=cfg.get("PORT") or 5432,
            )
            conn.close()
            print("Database is ready.", flush=True)
            return
        except Exception as exc:  # noqa: BLE001 — retry until timeout
            print(f"DB not ready ({attempt}): {exc}", flush=True)
            time.sleep(2)
    raise SystemExit("Database did not become ready in time.")


def main() -> None:
    wait_for_db()
    subprocess.check_call([sys.executable, "manage.py", "migrate", "--noinput"])
    if not sys.argv[1:]:
        raise SystemExit("No command provided to entrypoint")
    os.execvp(sys.argv[1], sys.argv[1:])


if __name__ == "__main__":
    main()
