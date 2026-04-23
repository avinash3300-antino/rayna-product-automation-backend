"""Seed remaining 2 London categories (Luxury & Private, Seasonal & Events)."""
import asyncio
import hashlib
import logging
import uuid
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("seed_remaining")

LONDON_CITY_ID = "c5cda0a7-0b95-4a26-a8b4-1001b81014a5"

CATEGORIES = [
    {
        "category": "Luxury & Private",
        "name": "Private London Helicopter Flight",
        "slug": "private-london-helicopter-flight-central-london",
        "description_short": "Soar above London in a private helicopter with breathtaking views of the Shard, Tower Bridge, Buckingham Palace, and the Eye.",
        "description_long": "Experience London from the sky on this exclusive private helicopter tour. Take off from Battersea Heliport and soar over central London, enjoying unobstructed views of the Thames, Houses of Parliament, Buckingham Palace, Tower Bridge, the Shard, and the London Eye. Your private charter means only your group on board with a window seat guaranteed. Perfect for proposals, anniversaries, or a once-in-a-lifetime London experience. Includes champagne on landing.",
        "activity_type": "helicopter_tour",
        "price_adult": 1100.00,
        "price_child": 950.00,
        "duration_minutes": 30,
        "address": "Battersea Heliport, Bridges Ct, London SW11 3BE",
        "lat": 51.4711, "lng": -0.1756,
        "highlights": ["Private helicopter charter", "Central London flight path", "Views of all major landmarks", "Window seat guaranteed", "Champagne on landing"],
        "included": ["Private helicopter flight", "Pilot commentary", "Champagne reception", "Safety briefing", "Photos from pilot"],
        "excluded": ["Hotel transfer", "Video recording", "Additional flights"],
        "source_urls": ["https://www.getyourguide.com/london-l57/london-helicopter-tour", "https://www.viator.com/tours/London/Helicopter-Tour"],
        "search_query": "london helicopter tour aerial view luxury private",
        "operator_name": "The London Helicopter",
        "meta_title": "Private London Helicopter | Rayna Tours",
        "timeline": [
            {"order": 1, "time_label": "Arrival", "title": "Check-in at Heliport", "description": "Safety briefing and champagne"},
            {"order": 2, "time_label": "10 min", "title": "Take Off", "description": "Lift off over the Thames"},
            {"order": 3, "time_label": "20 min", "title": "Central London Circuit", "description": "All major landmarks"},
            {"order": 4, "time_label": "30 min", "title": "Landing & Photos", "description": "Return to Battersea Heliport"},
        ],
    },
    {
        "category": "Seasonal & Events",
        "name": "London Christmas Lights Walking Tour",
        "slug": "london-christmas-lights-walking-tour-mulled-wine",
        "description_short": "Stroll through London's dazzling Christmas light displays from Oxford Street to Covent Garden with festive mulled wine stops.",
        "description_long": "Immerse yourself in London's magical Christmas atmosphere on this festive walking tour. See the spectacular light displays on Oxford Street, Carnaby Street, and Regent Street. Visit the iconic Covent Garden Christmas tree and decorations, explore the winter market at Leicester Square, and warm up with mulled wine at two traditional stops. Your guide shares the stories behind London's Christmas traditions dating back to the Victorian era.",
        "activity_type": "seasonal_tour",
        "price_adult": 95.00,
        "price_child": 65.00,
        "duration_minutes": 150,
        "address": "Oxford Circus Station, London W1B 3AG",
        "lat": 51.5152, "lng": -0.1415,
        "highlights": ["Oxford Street Christmas lights", "Carnaby Street decorations", "Covent Garden Christmas tree", "Two mulled wine stops", "Leicester Square Winter Market"],
        "included": ["Expert guide", "Two mulled wines", "Festive treats", "Walking route map"],
        "excluded": ["Additional drinks", "Shopping time", "Hotel transfer"],
        "source_urls": ["https://www.getyourguide.com/london-l57/christmas-lights-tour", "https://www.viator.com/tours/London/Christmas-Walking-Tour"],
        "search_query": "london christmas lights decorations festive winter",
        "operator_name": "London Christmas Tours",
        "meta_title": "London Christmas Lights Tour | Rayna Tours",
        "timeline": [
            {"order": 1, "time_label": "5:00 PM", "title": "Meet at Oxford Circus", "description": "Start at the Oxford Street lights"},
            {"order": 2, "time_label": "5:30 PM", "title": "Carnaby Street", "description": "Famous themed decorations"},
            {"order": 3, "time_label": "6:15 PM", "title": "Regent Street & Mulled Wine", "description": "First warm-up stop"},
            {"order": 4, "time_label": "7:00 PM", "title": "Covent Garden", "description": "Christmas tree and final mulled wine"},
        ],
    },
]


def _dedup_hash(name, city, category):
    raw = f"{name.lower().strip()}|{city.lower().strip()}|{category.lower().strip()}"
    return hashlib.md5(raw.encode()).hexdigest()


async def seed():
    from app.db.base import async_session_factory
    from app.db.models.activities import Activity, ActivityTimeline
    from app.db.models.reviews import ProductReview
    from app.services.image_service import fetch_and_upload_images

    city_id = uuid.UUID(LONDON_CITY_ID)

    for i, cat in enumerate(CATEGORIES):
        logger.info("[%d/2] Processing: %s — %s", i + 1, cat["category"], cat["name"])
        product_id = str(uuid.uuid4())

        logger.info("  Searching Freepik for '%s'...", cat["search_query"])
        try:
            gallery = await fetch_and_upload_images(
                product_name=cat["search_query"],
                city="London",
                product_id=product_id,
                product_type="activities",
                num_images=8,
            )
            logger.info("  Got %d images", len(gallery))
        except Exception as exc:
            logger.error("  Image fetch failed: %s", exc)
            gallery = []

        cover_url = gallery[0]["url"] if gallery else None

        async with async_session_factory() as db:
            activity = Activity(
                id=uuid.UUID(product_id),
                name=cat["name"],
                slug=cat["slug"],
                city_id=city_id,
                category=cat["category"],
                sub_category=None,
                activity_type=cat["activity_type"],
                tags=[cat["category"].lower().replace(" & ", "-").replace(" ", "-")],
                status="active",
                description_short=cat["description_short"],
                description_long=cat["description_long"],
                highlights=cat["highlights"],
                included=cat["included"],
                excluded=cat["excluded"],
                what_to_bring="Comfortable walking shoes, weather-appropriate clothing",
                important_notes=["Please arrive 15 minutes before the scheduled start time", "A valid photo ID may be required"],
                redemption_instructions=["Show your e-ticket on your mobile device", "Exchange at the meeting point for your pass"],
                price_adult=cat["price_adult"],
                price_child=cat["price_child"],
                price_infant=0,
                price_group=None,
                price_original=round(cat["price_adult"] * 1.15, 2),
                currency="AED",
                price_type="per_person",
                discount_pct=13.00,
                price_from=cat["price_adult"],
                duration_minutes=cat["duration_minutes"],
                start_times=["09:00", "14:00"],
                operating_days=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
                instant_confirmation=True,
                free_cancellation=True,
                cancellation_hours=24,
                cancellation_policy="Free cancellation up to 24 hours before the experience starts.",
                min_participants=1,
                max_participants=25,
                advance_booking_days=1,
                country="United Kingdom",
                city="London",
                area="Central London",
                address=cat["address"],
                lat=cat["lat"],
                lng=cat["lng"],
                maps_link=f"https://www.google.com/maps?q={cat['lat']},{cat['lng']}",
                meeting_point_name=cat["address"].split(",")[0],
                meeting_point_desc=f"Meet at {cat['address'].split(',')[0]}",
                nearby_landmark=cat["address"].split(",")[0],
                pickup_available=False,
                pickup_locations=None,
                hotel_pickup_included=False,
                dropoff_available=False,
                refund_policy_details="Full refund if cancelled 24 hours before.",
                min_age=3,
                max_age=99,
                fitness_level="easy",
                difficulty="easy",
                pregnancy_restriction=False,
                wheelchair_access="partially",
                languages=["English"],
                dress_code_note=None,
                cover_image_url=cover_url,
                gallery_json=gallery if gallery else None,
                video_url=None,
                rating=4.60,
                review_count=5,
                rating_5=3,
                rating_4=1,
                rating_3=1,
                rating_2=0,
                rating_1=0,
                review_snippets=[
                    {"text": "Absolutely fantastic experience!", "author": "Sarah M.", "rating": 5},
                    {"text": "Great value for money, highly recommend.", "author": "James T.", "rating": 5},
                    {"text": "Well organized and the guide was excellent.", "author": "Emma L.", "rating": 4},
                ],
                meta_title=cat["meta_title"],
                meta_description=cat["description_short"][:155],
                focus_keyword=cat["category"].lower(),
                json_ld=None,
                canonical_url=None,
                source_url=cat["source_urls"][0],
                source_urls=cat["source_urls"],
                source_type="aggregator",
                operator_name=cat["operator_name"],
                operator_website=None,
                operator_established_year=None,
                operator_certifications=None,
                verified=False,
                dedup_hash=_dedup_hash(cat["name"], "London", cat["category"]),
                quality_score=72,
                other_attributes=None,
            )
            db.add(activity)
            await db.flush()

            for t in cat.get("timeline", []):
                tl = ActivityTimeline(
                    activity_id=uuid.UUID(product_id),
                    order=t["order"],
                    time_label=t.get("time_label"),
                    title=t["title"],
                    description=t.get("description"),
                )
                db.add(tl)

            sample_reviews = [
                {"name": "Sarah Mitchell", "rating": 5.0, "title": "Amazing experience!", "text": f"The {cat['name']} was absolutely incredible. Everything was well-organized and our guide was very knowledgeable. Would definitely recommend to anyone visiting London.", "platform": "tripadvisor"},
                {"name": "James Thompson", "rating": 5.0, "title": "Highly recommended", "text": f"One of the best things we did in London. The {cat['category'].lower()} experience exceeded our expectations. Great value for money.", "platform": "google"},
                {"name": "Emma Lewis", "rating": 4.0, "title": "Very enjoyable", "text": f"Had a wonderful time. The only minor issue was the waiting time at the start, but once it got going, it was brilliant.", "platform": "tripadvisor"},
                {"name": "David Chen", "rating": 5.0, "title": "Must-do in London!", "text": f"If you're visiting London, this is a must. The {cat['name']} gives you a genuine London experience. Our group had a fantastic time.", "platform": "google"},
                {"name": "Olivia Martinez", "rating": 4.0, "title": "Great day out", "text": f"Really enjoyed the experience. Well worth the price. Just make sure to book in advance as it fills up quickly.", "platform": "tripadvisor"},
            ]
            for rev in sample_reviews:
                review = ProductReview(
                    product_type="activities",
                    product_id=uuid.UUID(product_id),
                    reviewer_name=rev["name"],
                    rating=rev["rating"],
                    review_title=rev["title"],
                    review_text=rev["text"],
                    source_platform=rev["platform"],
                    verified=True,
                    language="en",
                )
                db.add(review)

            await db.flush()
            await db.commit()
            logger.info("  Done!")

        if i < len(CATEGORIES) - 1:
            await asyncio.sleep(2)

    logger.info("DONE! Remaining 2 categories seeded.")


if __name__ == "__main__":
    asyncio.run(seed())
