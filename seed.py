"""Seed script: creates 5 roles + admin user."""
import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.db.base import async_session_factory, engine
from app.db.models.auth import AuthRole, AuthUser, AuthUserRole

ROLES = [
    ("admin", "Admin"),
    ("product_manager", "Product Manager"),
    ("content_reviewer", "Content Reviewer"),
    ("classification_reviewer", "Classification Reviewer"),
    ("read_only", "Read Only"),
]

ADMIN_EMAIL = "admin@raynatours.com"
ADMIN_PASSWORD = "Admin@1234"
ADMIN_NAME = "Rayna Admin"


async def seed():
    async with async_session_factory() as db:
        # 1. Create roles
        for code, name in ROLES:
            exists = await db.execute(select(AuthRole).where(AuthRole.code == code))
            if not exists.scalar_one_or_none():
                db.add(AuthRole(code=code, name=name))
                print(f"  Created role: {code}")
            else:
                print(f"  Role exists:  {code}")
        await db.flush()

        # 2. Create admin user
        existing_admin = await db.execute(
            select(AuthUser).where(AuthUser.email == ADMIN_EMAIL)
        )
        admin = existing_admin.scalar_one_or_none()

        if not admin:
            admin = AuthUser(
                email=ADMIN_EMAIL,
                full_name=ADMIN_NAME,
                password_hash=hash_password(ADMIN_PASSWORD),
                status="active",
            )
            db.add(admin)
            await db.flush()
            print(f"  Created admin user: {ADMIN_EMAIL}")
        else:
            print(f"  Admin exists: {ADMIN_EMAIL}")

        # 3. Assign admin role
        admin_role = (
            await db.execute(select(AuthRole).where(AuthRole.code == "admin"))
        ).scalar_one()

        existing_assignment = await db.execute(
            select(AuthUserRole).where(
                AuthUserRole.user_id == admin.id,
                AuthUserRole.role_id == admin_role.id,
            )
        )
        if not existing_assignment.scalar_one_or_none():
            db.add(AuthUserRole(
                user_id=admin.id,
                role_id=admin_role.id,
                assigned_by=admin.id,
            ))
            print("  Assigned admin role to admin user")

        await db.commit()
        print("\nSeed complete!")
        print(f"  Login: {ADMIN_EMAIL} / {ADMIN_PASSWORD}")


if __name__ == "__main__":
    asyncio.run(seed())
