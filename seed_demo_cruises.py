"""
Seed two demo dinner cruises: Thames (London) and Nile (Cairo).
Run once: python seed_demo_cruises.py
"""

import json
import uuid
import hashlib
import psycopg2

DATABASE_URL = "postgresql://postgres:Avinash1234@localhost:5432/rayna_db"

LONDON_CITY_ID = "c5cda0a7-0b95-4a26-a8b4-1001b81014a5"
CAIRO_CITY_ID = "941c503c-82a0-4a76-80ae-f8bb78cd7437"


def make_hash(name, city):
    return hashlib.md5(f"{name}:{city}".encode()).hexdigest()


CRUISES = [
    # ── London Thames Dinner Cruise ──────────────────────────────
    {
        "id": str(uuid.uuid4()),
        "name": "Thames Royal Dinner Cruise",
        "slug": "thames-royal-dinner-cruise-london",
        "city_id": LONDON_CITY_ID,
        "category": "Cruise",
        "sub_category": "Dinner",
        "cruise_class": "Premium",
        "cruise_type": "dinner",
        "tags": json.dumps(["dinner cruise", "thames", "london", "romantic", "sightseeing"]),
        "status": "published",
        "description_short": "Glide along the River Thames on a luxurious dinner cruise past London's most iconic landmarks — Big Ben, the Tower of London, and the London Eye — all while enjoying a freshly prepared 3-course meal and live entertainment.",
        "description_long": """<p>Experience London from its most enchanting perspective aboard the Thames Royal Dinner Cruise. As the sun sets over the city skyline, step onto a beautifully appointed modern vessel and embark on a 2.5-hour journey through the heart of London.</p>
<ul>
<li><strong>Stunning views:</strong> Sail past the Houses of Parliament, Tower Bridge, the Shard, Canary Wharf, and the Globe Theatre as they light up against the evening sky</li>
<li><strong>Gourmet dining:</strong> Savour a freshly prepared 3-course dinner featuring seasonal British ingredients, with vegetarian and dietary options available on request</li>
<li><strong>Live entertainment:</strong> Enjoy a live jazz ensemble and a resident DJ who keeps the atmosphere elegant yet vibrant throughout the evening</li>
<li><strong>Welcome drink:</strong> Begin your evening with a complimentary glass of prosecco as you settle into your reserved window-side table</li>
<li><strong>Climate-controlled comfort:</strong> The glass-enclosed upper deck offers panoramic views regardless of the weather, while the open-air observation area is perfect for photos</li>
</ul>
<p>Whether you are celebrating an anniversary, planning a memorable date night, or simply treating yourself to an unforgettable London evening, this dinner cruise delivers elegance, flavour, and views in equal measure.</p>""",
        "highlights": json.dumps([
            "Sail past Big Ben, Tower Bridge, the London Eye, and the Shard",
            "3-course gourmet dinner with seasonal British cuisine",
            "Complimentary welcome glass of prosecco",
            "Live jazz band and resident DJ",
            "Glass-enclosed panoramic upper deck",
            "Window-side reserved seating"
        ]),
        "included": json.dumps([
            "2.5-hour Thames dinner cruise",
            "Welcome glass of prosecco",
            "3-course freshly prepared dinner",
            "Live jazz entertainment and DJ",
            "Reserved window-side table",
            "Access to open-air observation deck"
        ]),
        "excluded": json.dumps([
            "Hotel pickup and drop-off",
            "Additional alcoholic beverages (available at onboard bar)",
            "Gratuities"
        ]),
        "what_to_bring": "Smart-casual attire is recommended. Bring a light jacket for the open-air deck.",
        "important_notes": json.dumps([
            "Boarding begins 30 minutes before departure",
            "Photo ID required for all guests",
            "Not wheelchair accessible on the upper observation deck"
        ]),
        "price_adult": 89.00,
        "price_child": 49.00,
        "price_infant": 0.00,
        "price_original": 109.00,
        "currency": "GBP",
        "price_type": "per person",
        "discount_pct": 18.00,
        "price_from": 89.00,
        "duration_hours": 2.5,
        "number_of_nights": 0,
        "departure_times": json.dumps(["7:30 PM"]),
        "operating_days": json.dumps(["Monday", "Wednesday", "Thursday", "Friday", "Saturday"]),
        "seasonal_availability": "Year-round, daily sailings from April to October; reduced schedule November to March",
        "boarding_time": "7:00 PM",
        "instant_confirmation": True,
        "free_cancellation": True,
        "cancellation_hours": 24,
        "cancellation_policy": "Free cancellation up to 24 hours before departure. No refund for cancellations within 24 hours.",
        "advance_booking_days": 1,
        "country": "United Kingdom",
        "city": "London",
        "area": "Westminster",
        "address": "Victoria Embankment, Westminster Pier, London WC2N 6NU",
        "lat": 51.504170,
        "lng": -0.122710,
        "maps_link": "https://maps.google.com/?q=51.504170,-0.122710",
        "boarding_point_name": "Westminster Pier",
        "boarding_point_description": "Located on Victoria Embankment, directly opposite the London Eye. Nearest tube: Westminster (District, Circle, Jubilee lines).",
        "nearby_landmark": "London Eye",
        "pickup_available": False,
        "vessel_name": "HMS Royale",
        "vessel_type": "Catamaran",
        "vessel_capacity": 180,
        "deck_count": 2,
        "onboard_facilities": json.dumps(["Full-service bar", "Live music stage", "Open-air observation deck", "Climate-controlled dining hall", "Restrooms"]),
        "meal_included": True,
        "meal_type": "Set Menu",
        "entertainment_included": True,
        "entertainment_details": json.dumps(["Live jazz ensemble", "Resident DJ"]),
        "wifi_available": True,
        "route_description": "Westminster Pier → Houses of Parliament → London Eye → Blackfriars Bridge → St Paul's Cathedral → Millennium Bridge → Shakespeare's Globe → Tate Modern → HMS Belfast → Tower Bridge → Canary Wharf → Greenwich (turnaround) → return to Westminster Pier",
        "min_age": 5,
        "dress_code": "Smart casual",
        "wheelchair_accessible": "Partially",
        "languages": json.dumps(["en"]),
        "operator_name": "Thames Luxury Cruises Ltd",
        "cover_image_url": "https://images.unsplash.com/photo-1513635269975-59663e0ac1ad?w=800&q=80",
        "gallery_json": json.dumps([
            {"url": "https://images.unsplash.com/photo-1513635269975-59663e0ac1ad?w=800&q=80", "alt": "London skyline at night from the Thames"},
            {"url": "https://images.unsplash.com/photo-1505761671935-60b3a7427bad?w=800&q=80", "alt": "Tower Bridge illuminated at night"},
            {"url": "https://images.unsplash.com/photo-1486299267070-83823f5448dd?w=800&q=80", "alt": "Big Ben and Houses of Parliament at dusk"},
        ]),
        "rating": 4.70,
        "review_count": 342,
        "rating_5": 210,
        "rating_4": 95,
        "rating_3": 27,
        "rating_2": 7,
        "rating_1": 3,
        "review_snippets": json.dumps([
            "Absolutely magical evening — the views of Tower Bridge lit up were breathtaking.",
            "Food was excellent and the jazz band set the perfect mood.",
            "Best way to see London at night. Highly recommend the window seats!"
        ]),
        "meta_title": "Thames Royal Dinner Cruise London | Book Online",
        "meta_description": "Enjoy a luxury dinner cruise on the River Thames with live jazz, a 3-course meal, and panoramic views of London's iconic landmarks. Book now!",
        "focus_keyword": "thames dinner cruise london",
        "source_url": "https://demo.rayna.com/cruises/thames-dinner",
        "source_type": "manual",
        "dedup_hash": make_hash("Thames Royal Dinner Cruise", "London"),
        "quality_score": 92,
    },

    # ── Cairo Nile Dinner Cruise ─────────────────────────────────
    {
        "id": str(uuid.uuid4()),
        "name": "Nile Pharaoh Dinner Cruise",
        "slug": "nile-pharaoh-dinner-cruise-cairo",
        "city_id": CAIRO_CITY_ID,
        "category": "Cruise",
        "sub_category": "Dinner",
        "cruise_class": "Premium",
        "cruise_type": "dinner",
        "tags": json.dumps(["dinner cruise", "nile", "cairo", "belly dance", "oriental"]),
        "status": "published",
        "description_short": "Cruise the legendary Nile River through the heart of Cairo aboard a grand floating restaurant. Enjoy an open buffet of Egyptian and international cuisine, a mesmerising belly dance show, and a whirling Tanoura performance under the stars.",
        "description_long": """<p>Step aboard the Nile Pharaoh — Cairo's most celebrated dinner cruise vessel — for an unforgettable evening on the world's longest river. This 3-hour voyage combines the best of Egyptian hospitality with world-class entertainment and cuisine.</p>
<ul>
<li><strong>Spectacular Nile views:</strong> Watch Cairo's glittering skyline unfold as you sail past the Cairo Tower, the Egyptian Museum neighbourhood, and the illuminated Qasr El Nil Bridge</li>
<li><strong>Lavish open buffet:</strong> Feast on an extensive spread of traditional Egyptian dishes — koshari, grilled kofta, molokhia — alongside international favourites, salads, and an indulgent dessert station</li>
<li><strong>Live entertainment:</strong> Be captivated by a professional belly dance performance, a hypnotic Tanoura spinning show, and a live oriental music band that fills the night air with authentic melodies</li>
<li><strong>Open-air upper deck:</strong> After dinner, head to the rooftop terrace for panoramic views of the Nile and fresh evening breezes — the perfect spot for photos</li>
<li><strong>Hotel transfers:</strong> Complimentary round-trip transfers from major Cairo and Giza hotels make your evening completely hassle-free</li>
</ul>
<p>From the moment you board to the final note of music, the Nile Pharaoh Dinner Cruise delivers an authentic, vibrant, and utterly memorable Cairo night out.</p>""",
        "highlights": json.dumps([
            "3-hour cruise on the Nile through central Cairo",
            "Open buffet with Egyptian and international cuisine",
            "Live belly dance and Tanoura spinning show",
            "Live oriental music band",
            "Open-air rooftop deck with panoramic Nile views",
            "Complimentary hotel pickup and drop-off from Cairo/Giza hotels"
        ]),
        "included": json.dumps([
            "3-hour Nile dinner cruise",
            "Open buffet dinner (Egyptian & international)",
            "Soft drinks, tea, and coffee",
            "Live belly dance performance",
            "Tanoura spinning show",
            "Live oriental music band",
            "Round-trip hotel transfers (Cairo & Giza)"
        ]),
        "excluded": json.dumps([
            "Alcoholic beverages (available for purchase onboard)",
            "Personal expenses and souvenirs",
            "Gratuities for crew"
        ]),
        "what_to_bring": "Comfortable clothing suitable for an evening out. A light layer for the upper deck.",
        "important_notes": json.dumps([
            "Hotel pickup begins approximately 1 hour before sailing",
            "Boarding at the Nile City dock from 7:00 PM",
            "Entertainment schedule may vary on Fridays (weekend)"
        ]),
        "price_adult": 45.00,
        "price_child": 25.00,
        "price_infant": 0.00,
        "price_original": 60.00,
        "currency": "USD",
        "price_type": "per person",
        "discount_pct": 25.00,
        "price_from": 45.00,
        "duration_hours": 3.0,
        "number_of_nights": 0,
        "departure_times": json.dumps(["8:00 PM"]),
        "operating_days": json.dumps(["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]),
        "seasonal_availability": "Year-round, daily sailings",
        "boarding_time": "7:30 PM",
        "instant_confirmation": True,
        "free_cancellation": True,
        "cancellation_hours": 48,
        "cancellation_policy": "Free cancellation up to 48 hours before departure. 50% refund for cancellations within 24–48 hours.",
        "advance_booking_days": 1,
        "country": "Egypt",
        "city": "Cairo",
        "area": "Nile City",
        "address": "Nile City Towers Corniche, Ramlet Beaulac, Cairo",
        "lat": 30.071500,
        "lng": 31.224700,
        "maps_link": "https://maps.google.com/?q=30.071500,31.224700",
        "boarding_point_name": "Nile City Dock",
        "boarding_point_description": "Located at the Corniche next to Nile City Towers. Easily accessible from downtown Cairo and Giza.",
        "nearby_landmark": "Cairo Tower",
        "pickup_available": True,
        "pickup_points": json.dumps(["Cairo city centre hotels", "Giza Pyramids area hotels", "Zamalek hotels"]),
        "vessel_name": "Nile Pharaoh",
        "vessel_type": "Riverboat",
        "vessel_capacity": 250,
        "deck_count": 3,
        "onboard_facilities": json.dumps(["Open buffet stations", "Full-service bar", "Live performance stage", "Open-air rooftop deck", "Air-conditioned dining halls", "Restrooms"]),
        "meal_included": True,
        "meal_type": "Buffet",
        "entertainment_included": True,
        "entertainment_details": json.dumps(["Belly dance show", "Tanoura spinning performance", "Live oriental music band"]),
        "wifi_available": False,
        "route_description": "Nile City Dock → Cairo Tower → Qasr El Nil Bridge → Garden City waterfront → Old Cairo view → University Bridge (turnaround) → return to Nile City Dock",
        "min_age": 3,
        "dress_code": "Casual",
        "wheelchair_accessible": "Yes",
        "languages": json.dumps(["en", "ar"]),
        "operator_name": "Nile Pharaoh Cruises",
        "cover_image_url": "https://images.unsplash.com/photo-1572252009286-268acec5ca0a?w=800&q=80",
        "gallery_json": json.dumps([
            {"url": "https://images.unsplash.com/photo-1572252009286-268acec5ca0a?w=800&q=80", "alt": "Nile river cruise at sunset in Cairo"},
            {"url": "https://images.unsplash.com/photo-1553913861-c0a813844032?w=800&q=80", "alt": "Cairo Tower lit up at night from the Nile"},
            {"url": "https://images.unsplash.com/photo-1568322503122-d1e2c2164fe1?w=800&q=80", "alt": "Traditional Egyptian dinner spread"},
        ]),
        "rating": 4.50,
        "review_count": 518,
        "rating_5": 280,
        "rating_4": 150,
        "rating_3": 55,
        "rating_2": 23,
        "rating_1": 10,
        "review_snippets": json.dumps([
            "The belly dance show was incredible — an absolute must-do in Cairo!",
            "Amazing food, beautiful views, and the Tanoura dancer was mesmerising.",
            "Hotel pickup was on time and the whole experience was seamless."
        ]),
        "meta_title": "Nile Pharaoh Dinner Cruise Cairo | Book Online",
        "meta_description": "Enjoy an authentic Nile dinner cruise in Cairo with belly dance, Tanoura show, open buffet, and live music. Hotel transfers included. Book now!",
        "focus_keyword": "nile dinner cruise cairo",
        "source_url": "https://demo.rayna.com/cruises/nile-dinner",
        "source_type": "manual",
        "dedup_hash": make_hash("Nile Pharaoh Dinner Cruise", "Cairo"),
        "quality_score": 88,
    },
]

# ── Itinerary items ──────────────────────────────────────────────
ITINERARIES = {
    "thames-royal-dinner-cruise-london": [
        {"order": 1, "time_label": "7:00 PM", "port_or_stop": "Westminster Pier", "description": "Boarding and welcome prosecco reception"},
        {"order": 2, "time_label": "7:30 PM", "port_or_stop": "Houses of Parliament", "description": "Depart Westminster — pass Big Ben and the Houses of Parliament"},
        {"order": 3, "time_label": "7:45 PM", "port_or_stop": "St Paul's & Millennium Bridge", "description": "First course served as you glide past St Paul's Cathedral"},
        {"order": 4, "time_label": "8:15 PM", "port_or_stop": "Tower Bridge", "description": "Main course served with Tower Bridge as the backdrop"},
        {"order": 5, "time_label": "8:45 PM", "port_or_stop": "Canary Wharf", "description": "Live jazz performance and dessert service"},
        {"order": 6, "time_label": "9:30 PM", "port_or_stop": "Greenwich turnaround", "description": "Vessel turns — DJ set begins on the return leg"},
        {"order": 7, "time_label": "10:00 PM", "port_or_stop": "Westminster Pier", "description": "Arrive back at Westminster Pier. Disembarkation."},
    ],
    "nile-pharaoh-dinner-cruise-cairo": [
        {"order": 1, "time_label": "7:00 PM", "port_or_stop": "Hotel pickup", "description": "Complimentary pickup from your Cairo or Giza hotel"},
        {"order": 2, "time_label": "7:30 PM", "port_or_stop": "Nile City Dock", "description": "Boarding and welcome drinks on the upper deck"},
        {"order": 3, "time_label": "8:00 PM", "port_or_stop": "Cairo Tower", "description": "Depart dock — open buffet dinner is served"},
        {"order": 4, "time_label": "8:45 PM", "port_or_stop": "Qasr El Nil Bridge", "description": "Live oriental music band performs during dinner"},
        {"order": 5, "time_label": "9:15 PM", "port_or_stop": "Garden City waterfront", "description": "Belly dance show takes centre stage"},
        {"order": 6, "time_label": "9:45 PM", "port_or_stop": "University Bridge turnaround", "description": "Tanoura spinning performance on the return"},
        {"order": 7, "time_label": "10:30 PM", "port_or_stop": "Nile City Dock", "description": "Arrive back at dock. Transfer to hotel."},
    ],
}


def seed():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    for cruise in CRUISES:
        slug = cruise["slug"]
        cruise_id = cruise["id"]

        # Build column names and placeholders
        cols = list(cruise.keys())
        placeholders = ["%s"] * len(cols)

        sql = f"""
            INSERT INTO catalog_cruise_products ({', '.join(cols)})
            VALUES ({', '.join(placeholders)})
            ON CONFLICT (slug) DO NOTHING
        """
        cur.execute(sql, [cruise[c] for c in cols])
        print(f"  Inserted cruise: {cruise['name']}")

        # Insert itinerary
        for item in ITINERARIES.get(slug, []):
            cur.execute(
                """INSERT INTO catalog_cruise_itinerary
                   (id, cruise_id, "order", time_label, port_or_stop, description)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (str(uuid.uuid4()), cruise_id, item["order"],
                 item["time_label"], item["port_or_stop"], item["description"]),
            )
        print(f"    + {len(ITINERARIES.get(slug, []))} itinerary stops")

    conn.commit()
    cur.close()
    conn.close()
    print("\nDone — 2 demo dinner cruises seeded!")


if __name__ == "__main__":
    seed()
