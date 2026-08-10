"""Create the initial admin account after database setup.

Run from the backend directory:
    uv run python scripts/seed_admin.py

Credentials can be supplied through INITIAL_ADMIN_EMAIL and
INITIAL_ADMIN_PASSWORD or entered interactively.
"""

import asyncio
import getpass
import os
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv
from pydantic import EmailStr, TypeAdapter
from sqlalchemy import func, select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env", override=False)

from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.user import User


async def seed_admin(email: str, plain_password: str) -> bool:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(func.lower(User.email) == email.lower()))
        existing_account = result.scalar_one_or_none()

        if existing_account is not None:
            if existing_account.role == 1:
                print(f"Admin already exists: {email}. No changes were made.")
            else:
                print(
                    f"Cannot create admin: {email} is already registered as a regular user. "
                    "No changes were made."
                )
            return False

        hashed_password = hash_password(plain_password)
        db.add(User(
            id=uuid.uuid4(),
            email=email,
            first_name="Admin",
            last_name="User",
            password=hashed_password,
            role=1,
            is_verified=True,
            is_active=True,
            monthly_video_count=0,
        ))
        await db.commit()
        print(f"Admin created successfully: {email}")
        return True


async def main() -> None:
    email_value = os.getenv("INITIAL_ADMIN_EMAIL")
    password = os.getenv("INITIAL_ADMIN_PASSWORD")

    if not email_value:
        if not sys.stdin.isatty():
            raise SystemExit("INITIAL_ADMIN_EMAIL is required in non-interactive mode.")
        email_value = input("Admin email: ").strip()

    if not password:
        if not sys.stdin.isatty():
            raise SystemExit("INITIAL_ADMIN_PASSWORD is required in non-interactive mode.")
        password = getpass.getpass("Admin password: ")

    if len(password) < 12:
        raise SystemExit("Admin password must be at least 12 characters long.")

    email = TypeAdapter(EmailStr).validate_python(email_value).lower()
    await seed_admin(email, password)


if __name__ == "__main__":
    asyncio.run(main())
