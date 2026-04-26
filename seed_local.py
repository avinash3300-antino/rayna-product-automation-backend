"""Seed local rayna_db with test data for verifying all 6 feedback items."""

import asyncio
import hashlib
import json
import uuid

import bcrypt
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.db.models.auth import AuthRole, AuthUser, AuthUserRole
from app.db.models.destinations import CatalogDestination
from app.db.models.activities import Activity
from app.db.models.reviews import ProductReview

DB_URL = "postgresql+asyncpg://postgres:Avinash1234@localhost:5432/rayna_db"


async def main():
    engine = create_async_engine(DB_URL)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as db:
        from sqlalchemy import select

        # 1. Admin role + user (idempotent)
        result = await db.execute(select(AuthRole).where(AuthRole.code == "admin"))
        role = result.scalar_one_or_none()
        if not role:
            role = AuthRole(id=uuid.uuid4(), code="admin", name="Administrator")
            db.add(role)
            await db.flush()

        result = await db.execute(
            select(AuthUser).where(AuthUser.email == "admin@raynatours.com")
        )
        user = result.scalar_one_or_none()
        if not user:
            pw_hash = bcrypt.hashpw(b"admin123", bcrypt.gensalt()).decode()
            user = AuthUser(
                id=uuid.uuid4(),
                email="admin@raynatours.com",
                full_name="Admin User",
                password_hash=pw_hash,
                status="active",
            )
            db.add(user)
            await db.flush()

            link = AuthUserRole(user_id=user.id, role_id=role.id)
            db.add(link)
            await db.flush()
        print(f"Admin user: admin@raynatours.com / admin123")

        # 2. Destination (idempotent)
        result = await db.execute(
            select(CatalogDestination).where(CatalogDestination.code == "LON")
        )
        dest = result.scalar_one_or_none()
        if not dest:
            dest = CatalogDestination(
                id=uuid.uuid4(),
                code="LON",
                name="London",
                country_code="GB",
                country_name="United Kingdom",
                country_flag="GB",
                status="active",
                enabled_categories=["activities", "cruises"],
            )
            db.add(dest)
            await db.flush()
        city_id = dest.id
        print(f"Destination: London ({city_id})")

        # 3. 40 activities
        categories = ["tours", "attractions", "experiences", "shows", "outdoor"]
        for i in range(40):
            cat = categories[i % len(categories)]
            name = f"London {cat.title()} Activity {i+1}"
            slug = f"london-{cat}-activity-{i+1}"
            dedup = hashlib.md5(name.encode()).hexdigest()
            price = 30 + (i * 5)

            a = Activity(
                id=uuid.uuid4(),
                name=name,
                slug=slug,
                city_id=city_id,
                category=cat,
                activity_type="standard",
                status="active",
                description_short=f"A wonderful {cat} experience in London.",
                description_long=(
                    f"This is a detailed description for {name}. "
                    f"Experience the best of London with this amazing {cat} activity. "
                    "Our expert guides will take you through iconic locations. "
                    "You will visit historic landmarks, enjoy local cuisine, and learn "
                    "about the rich cultural heritage of London. The tour includes visits "
                    "to major attractions, hidden gems, and local favorites. Perfect for "
                    "families, couples, and solo travelers."
                ),
                highlights=["Expert local guides", "Skip-the-line access", "Small group experience"],
                included=["Professional guide", "Entry tickets", "Hotel pickup"],
                excluded=["Food and drinks", "Gratuities"],
                price_adult=price,
                currency="GBP",
                price_type="per_person",
                price_from=price,
                duration_minutes=180 + (i * 10),
                start_times=["09:00", "14:00"],
                operating_days=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
                country="United Kingdom",
                city="London",
                address=f"{100+i} Test Street, London",
                lat=51.5074 + (i * 0.001),
                lng=-0.1278 + (i * 0.001),
                languages=["English"],
                source_url=f"https://www.getyourguide.com/london/{slug}",
                source_urls=[
                    f"https://www.getyourguide.com/london-l57/{slug}-t{100+i}",
                    f"https://www.viator.com/tours/London/{slug}/d737-{100+i}",
                ],
                source_type="scraping",
                instant_confirmation=(i % 3 == 0),
                free_cancellation=(i % 2 == 0),
                verified=False,
                dedup_hash=dedup,
                quality_score=60 + (i % 30),
                review_count=0,
                rating_5=0,
                rating_4=0,
                rating_3=0,
                rating_2=0,
                rating_1=0,
                pickup_available=False,
                hotel_pickup_included=False,
                dropoff_available=False,
                pregnancy_restriction=False,
                cover_image_url=f"https://picsum.photos/seed/cover-{slug}/400/300",
                gallery_json=[
                    f"https://picsum.photos/seed/{slug}-1/800/600",
                    f"https://picsum.photos/seed/{slug}-2/800/600",
                    f"https://picsum.photos/seed/{slug}-3/800/600",
                    f"https://picsum.photos/seed/{slug}-4/800/600",
                ],
            )
            db.add(a)

            # Add 3 reviews for every 5th activity
            if i % 5 == 0:
                for j in range(3):
                    review = ProductReview(
                        id=uuid.uuid4(),
                        product_type="activities",
                        product_id=a.id,
                        reviewer_name=f"Reviewer {j+1}",
                        rating=4.0 + (j * 0.5),
                        review_title=f"Great {cat} experience!",
                        review_text=(
                            f"Had an amazing time on this {cat} activity in London. "
                            "The guide was very knowledgeable and friendly. "
                            "Would highly recommend to anyone visiting the city."
                        ),
                        source_platform=["google", "tripadvisor", "trustpilot"][j],
                        verified=(j == 0),
                        language="en",
                    )
                    db.add(review)
                a.review_count = 3
                a.rating = 4.5

        await db.commit()

        print("Seeded 40 activities (8 with reviews)")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
