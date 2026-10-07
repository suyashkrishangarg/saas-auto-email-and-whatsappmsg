from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.core.database import AsyncSessionLocal, init_db
from app.core.security import hash_password
from app.models.user import Role, User


async def ensure_superuser(email: str, password: str) -> None:
    await init_db()
    async with AsyncSessionLocal() as db:
        user = (
            (await db.execute(select(User).where(User.email == email.lower()))).scalar_one_or_none()
        )
        if user:
            user.hashed_password = hash_password(password)
            user.role = Role.SUPER_ADMIN
            user.is_active = True
            action = "updated"
        else:
            user = User(
                email=email.lower(),
                hashed_password=hash_password(password),
                role=Role.SUPER_ADMIN,
                is_active=True,
            )
            db.add(user)
            await db.flush()
            user.forwarding_alias = f"notices-{str(user.id)[:8]}@inbound.ramyaai.tech"
            action = "created"
        await db.commit()
        print(f"Super admin {action}: {email}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 3:
        print("Usage: python -m scripts.seed_superuser <email> <password>")
        sys.exit(1)
    asyncio.run(ensure_superuser(sys.argv[1], sys.argv[2]))
