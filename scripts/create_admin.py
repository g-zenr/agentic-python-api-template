"""Create or promote an admin user (idempotent, audited as SYSTEM).

Usage: `python scripts/create_admin.py --email X [--promote]` (or `make create-admin`).
Password comes from ADMIN_PASSWORD or an interactive prompt (twice).
"""

import argparse
import asyncio
import getpass
import os

from app.core.database import connect_db, disconnect_db
from app.features.users.service import create_admin


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or promote an admin user.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--promote", action="store_true")
    args = parser.parse_args()
    password = os.environ.get("ADMIN_PASSWORD") or getpass.getpass("Password: ")
    if password != (os.environ.get("ADMIN_PASSWORD") or getpass.getpass("Confirm: ")):
        raise SystemExit("passwords do not match")
    asyncio.run(_run(args.email, password, args.promote))


async def _run(email: str, password: str, promote: bool) -> None:
    await connect_db()
    try:
        await create_admin(email, password, promote)
        print(f"admin ready: {email}")
    finally:
        await disconnect_db()


if __name__ == "__main__":
    main()
