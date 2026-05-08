"""
Update demo cruises with real images (8+), real-style reviews (10+),
and proper source URLs.
"""

import json
import uuid
import psycopg2

DATABASE_URL = "postgresql://postgres:Avinash1234@localhost:5432/rayna_db"

THAMES_ID = "ef753c03-d6fa-4073-968f-c7cda9166c36"
NILE_ID = "695658d5-6fe5-4369-b1d2-c41fb4c710b7"

# ── Gallery Images (Unsplash – free to use) ──────────────────────

THAMES_GALLERY = [
    {"url": "https://images.unsplash.com/photo-1513635269975-59663e0ac1ad?w=800&q=80",  "alt": "London skyline and Thames at twilight"},
    {"url": "https://images.unsplash.com/photo-1505761671935-60b3a7427bad?w=800&q=80",  "alt": "Tower Bridge illuminated at night"},
    {"url": "https://images.unsplash.com/photo-1486299267070-83823f5448dd?w=800&q=80",  "alt": "Big Ben and Houses of Parliament at dusk"},
    {"url": "https://images.unsplash.com/photo-1529180979161-06b8b6d6a2ae?w=800&q=80",  "alt": "Thames river view with city lights"},
    {"url": "https://images.unsplash.com/photo-1533929736458-ca588d08c8be?w=800&q=80",  "alt": "London Eye lit up at night from the river"},
    {"url": "https://images.unsplash.com/photo-1517394834181-95ed159986c7?w=800&q=80",  "alt": "St Paul's Cathedral and Millennium Bridge"},
    {"url": "https://images.unsplash.com/photo-1543832923-44667a44c860?w=800&q=80",  "alt": "The Shard and London Bridge at sunset"},
    {"url": "https://images.unsplash.com/photo-1520986606214-8b456906c813?w=800&q=80",  "alt": "Westminster Bridge and Big Ben panoramic view"},
    {"url": "https://images.unsplash.com/photo-1448906654166-444d494666b3?w=800&q=80",  "alt": "Canary Wharf skyline from the Thames"},
    {"url": "https://images.unsplash.com/photo-1470145318530-84b0f28e4987?w=800&q=80",  "alt": "Tower of London from the river at dusk"},
]

NILE_GALLERY = [
    {"url": "https://images.unsplash.com/photo-1572252009286-268acec5ca0a?w=800&q=80",  "alt": "Nile river at golden sunset in Cairo"},
    {"url": "https://images.unsplash.com/photo-1553913861-c0a813844032?w=800&q=80",  "alt": "Cairo Tower illuminated at night"},
    {"url": "https://images.unsplash.com/photo-1568322503122-d1e2c2164fe1?w=800&q=80",  "alt": "Traditional Egyptian dinner buffet spread"},
    {"url": "https://images.unsplash.com/photo-1539768942893-daf53e736b68?w=800&q=80",  "alt": "Cairo city skyline along the Nile"},
    {"url": "https://images.unsplash.com/photo-1590059390047-f5e617a5e931?w=800&q=80",  "alt": "Qasr El Nil Bridge over the Nile at night"},
    {"url": "https://images.unsplash.com/photo-1503177119275-0aa32b3a9368?w=800&q=80",  "alt": "Egyptian felucca boats on the Nile at sunset"},
    {"url": "https://images.unsplash.com/photo-1562979314-bee7453e911c?w=800&q=80",  "alt": "Pyramids of Giza from the Nile valley"},
    {"url": "https://images.unsplash.com/photo-1608229614668-224b1e1d3b5d?w=800&q=80",  "alt": "Traditional Tanoura dancer performing in Cairo"},
    {"url": "https://images.unsplash.com/photo-1547471080-7cc2caa01a7e?w=800&q=80",  "alt": "Nile corniche promenade at dusk"},
    {"url": "https://images.unsplash.com/photo-1585019839589-2c2f0aa4e395?w=800&q=80",  "alt": "Aerial view of Cairo and the Nile river"},
]

# ── Reviews ──────────────────────────────────────────────────────

THAMES_REVIEWS = [
    {
        "reviewer_name": "Sarah Mitchell",
        "enriched_reviewer_name": "Sarah M.",
        "rating": 5.0,
        "review_title": "Magical evening on the Thames",
        "review_text": "We booked this for our anniversary and it exceeded all expectations. The views of Tower Bridge lit up were absolutely breathtaking. The 3-course meal was delicious — the pan-seared salmon was the highlight. The jazz band created the perfect atmosphere. Would book again in a heartbeat!",
        "enriched_text": "We booked this cruise for our anniversary and it exceeded all expectations. The views of Tower Bridge illuminated against the night sky were absolutely breathtaking. The three-course meal was delicious — the pan-seared salmon was the highlight of the evening. The live jazz band created the perfect atmosphere throughout. We would book again in a heartbeat!",
        "review_date": "2026-03-15",
        "source_platform": "google",
        "verified": True,
        "language": "en",
    },
    {
        "reviewer_name": "James O'Brien",
        "enriched_reviewer_name": "James O.",
        "rating": 5.0,
        "review_title": "Best way to see London at night",
        "review_text": "Absolutely stunning experience. Boarding was smooth, prosecco welcome was a nice touch. The food was really well prepared and the live music was top notch. Got some incredible photos of the city. Highly recommend the window seats!",
        "enriched_text": "An absolutely stunning experience from start to finish. Boarding was seamless and the complimentary prosecco welcome was a lovely touch. The food was beautifully prepared, and the live jazz was top-notch. I managed to capture some incredible photos of the city skyline. Highly recommend requesting the window-side seating!",
        "review_date": "2026-03-02",
        "source_platform": "tripadvisor",
        "verified": True,
        "language": "en",
    },
    {
        "reviewer_name": "Emma Richardson",
        "enriched_reviewer_name": "Emma R.",
        "rating": 4.0,
        "review_title": "Lovely cruise, minor wait at boarding",
        "review_text": "The cruise itself was wonderful. Great food, amazing views and the staff were lovely. Only slight negative was a 15-minute delay at boarding but once on board everything ran smoothly. The DJ set on the way back was a fun surprise.",
        "enriched_text": "The cruise itself was wonderful — great food, amazing views, and the staff were exceptionally attentive. The only slight downside was a 15-minute delay during boarding, but once on board everything ran smoothly. The DJ set on the return leg was an unexpectedly fun addition to the evening.",
        "review_date": "2026-02-20",
        "source_platform": "google",
        "verified": True,
        "language": "en",
    },
    {
        "reviewer_name": "David Chen",
        "enriched_reviewer_name": "David C.",
        "rating": 5.0,
        "review_title": "Perfect date night in London",
        "review_text": "Took my partner here for Valentine's. The ambiance was perfect — candlelit tables, soft jazz, and the Thames sparkling under the city lights. Food was excellent, especially the chocolate fondant. The staff even brought a small cake for us. Truly special.",
        "enriched_text": "I took my partner on this cruise for Valentine's Day and the ambiance was perfect — candlelit tables, soft jazz music, and the Thames sparkling beneath the city lights. The food was excellent, particularly the chocolate fondant dessert. The staff even arranged a small cake for us, which was a truly special and thoughtful touch.",
        "review_date": "2026-02-14",
        "source_platform": "tripadvisor",
        "verified": True,
        "language": "en",
    },
    {
        "reviewer_name": "Rachel Thompson",
        "enriched_reviewer_name": "Rachel T.",
        "rating": 5.0,
        "review_title": "Unforgettable birthday celebration",
        "review_text": "Booked for my mum's 60th birthday. She was absolutely blown away. The views are unbeatable — Big Ben, Tower Bridge, the Shard all lit up. Food was fresh and tasty, jazz band played Happy Birthday for her. Could not have asked for a better evening.",
        "enriched_text": "I booked this cruise for my mother's 60th birthday and she was absolutely blown away. The views are unbeatable — Big Ben, Tower Bridge, and the Shard all illuminated against the night sky. The food was fresh and delicious, and the jazz band even played Happy Birthday for her. I could not have asked for a more memorable evening.",
        "review_date": "2026-01-28",
        "source_platform": "google",
        "verified": True,
        "language": "en",
    },
    {
        "reviewer_name": "Mark Williams",
        "enriched_reviewer_name": "Mark W.",
        "rating": 4.0,
        "review_title": "Great experience, food could be warmer",
        "review_text": "Really enjoyed the cruise overall. The views from the panoramic deck are second to none. Jazz trio was brilliant. My only small complaint is that the main course arrived slightly lukewarm, but the taste was still good. Would definitely recommend.",
        "enriched_text": "I really enjoyed the cruise overall. The views from the panoramic glass deck are second to none, and the jazz trio performed brilliantly throughout the evening. My only minor observation was that the main course arrived slightly lukewarm, though the flavours were still very good. Would definitely recommend this experience.",
        "review_date": "2026-01-15",
        "source_platform": "trustpilot",
        "verified": True,
        "language": "en",
    },
    {
        "reviewer_name": "Priya Sharma",
        "enriched_reviewer_name": "Priya S.",
        "rating": 5.0,
        "review_title": "A must-do when visiting London!",
        "review_text": "Visiting from Mumbai and this was the highlight of our trip! The cruise was beautifully organised. Vegetarian options were available and delicious. Seeing Parliament and the Eye from the water at night is something else entirely. Brilliant experience.",
        "enriched_text": "Visiting London from Mumbai, this dinner cruise was the undisputed highlight of our trip. Everything was beautifully organised from boarding to disembarkation. Vegetarian options were readily available and truly delicious. Seeing the Houses of Parliament and the London Eye from the water at night is a completely different experience. Absolutely brilliant!",
        "review_date": "2025-12-30",
        "source_platform": "tripadvisor",
        "verified": True,
        "language": "en",
    },
    {
        "reviewer_name": "Oliver Grant",
        "enriched_reviewer_name": "Oliver G.",
        "rating": 5.0,
        "review_title": "Exceeded expectations",
        "review_text": "Was sceptical it might be a tourist trap but was genuinely impressed. Quality of food, the live entertainment, and the views are all top tier. The observation deck is a lovely bonus for photos. Staff were professional and friendly throughout.",
        "enriched_text": "I was initially sceptical that this might be a tourist trap, but I was genuinely impressed on every front. The quality of the food, the live entertainment, and the panoramic views are all top-tier. The open-air observation deck is a wonderful bonus for photography. Staff were professional and friendly throughout the entire evening.",
        "review_date": "2025-12-18",
        "source_platform": "google",
        "verified": True,
        "language": "en",
    },
    {
        "reviewer_name": "Chloe Baker",
        "enriched_reviewer_name": "Chloe B.",
        "rating": 4.0,
        "review_title": "Wonderful but a bit pricey",
        "review_text": "The experience itself was fantastic. Beautiful boat, great food, incredible views. The prosecco on arrival was a nice welcome. I did find it a bit on the expensive side especially with drinks on top, but for a special occasion it's worth every penny.",
        "enriched_text": "The experience itself was truly fantastic — a beautiful vessel, excellent food, and incredible views of London's skyline. The complimentary prosecco on arrival was a welcoming touch. I did find the overall cost a bit steep, especially with additional drinks on top, but for a special occasion it is absolutely worth every penny.",
        "review_date": "2025-12-05",
        "source_platform": "trustpilot",
        "verified": True,
        "language": "en",
    },
    {
        "reviewer_name": "Tom Henderson",
        "enriched_reviewer_name": "Tom H.",
        "rating": 5.0,
        "review_title": "Proposed on this cruise — she said yes!",
        "review_text": "I arranged a proposal during the cruise and the staff were incredible — they helped with flowers and timing it perfectly as we passed Tower Bridge. The food was lovely, the jazz created the perfect romantic mood. This will always be our special place. Thank you!",
        "enriched_text": "I arranged a proposal during this cruise and the staff were absolutely incredible. They helped coordinate flowers and timed the moment perfectly as we sailed past Tower Bridge. The food was lovely, and the live jazz created the ideal romantic atmosphere. This will forever be our special place. Thank you for making it unforgettable!",
        "review_date": "2025-11-22",
        "source_platform": "google",
        "verified": True,
        "language": "en",
    },
    {
        "reviewer_name": "Laura McDowell",
        "enriched_reviewer_name": "Laura M.",
        "rating": 5.0,
        "review_title": "Corporate event was a huge hit",
        "review_text": "Booked a group of 20 for a corporate Christmas dinner. The private section was perfect, food was excellent for a large group, and everyone loved the entertainment. Multiple colleagues said it was the best work event they'd attended. Will book again next year.",
        "enriched_text": "I booked a group of 20 for a corporate Christmas dinner on this cruise. The private section was perfectly set up, the food was excellent even for a large group, and everyone thoroughly enjoyed the live entertainment. Multiple colleagues said it was the best corporate event they had ever attended. We will absolutely be booking again next year.",
        "review_date": "2025-11-10",
        "source_platform": "tripadvisor",
        "verified": True,
        "language": "en",
    },
    {
        "reviewer_name": "Ahmed Khalil",
        "enriched_reviewer_name": "Ahmed K.",
        "rating": 4.0,
        "review_title": "Enjoyable evening cruise",
        "review_text": "Nice experience overall. The glass-enclosed deck is great in winter — warm and still get the views. Food was good quality British cuisine. The only thing I'd change is having the jazz play a bit softer during dinner so you can chat more easily. Otherwise great night.",
        "enriched_text": "A very enjoyable evening cruise experience overall. The glass-enclosed deck is brilliant during winter — warm and comfortable while still offering full panoramic views. The food was high-quality British cuisine. The only thing I would adjust is having the jazz play a touch softer during dinner to allow for easier conversation. Otherwise, a thoroughly great night out.",
        "review_date": "2025-10-28",
        "source_platform": "google",
        "verified": True,
        "language": "en",
    },
]

NILE_REVIEWS = [
    {
        "reviewer_name": "Jennifer Adams",
        "enriched_reviewer_name": "Jennifer A.",
        "rating": 5.0,
        "review_title": "Absolutely magical Nile experience",
        "review_text": "This was the highlight of our entire Egypt trip. The belly dance show was mesmerising, the food spread was enormous with so many authentic dishes, and the views of Cairo at night from the river are something you'll never forget. Hotel pickup was punctual. Highly recommended!",
        "enriched_text": "This dinner cruise was undoubtedly the highlight of our entire Egypt trip. The belly dance show was utterly mesmerising, the open buffet was enormous with a wonderful selection of authentic Egyptian dishes, and the views of Cairo illuminated at night from the river are simply unforgettable. Hotel pickup was punctual and hassle-free. Highly recommended!",
        "review_date": "2026-03-20",
        "source_platform": "google",
        "verified": True,
        "language": "en",
    },
    {
        "reviewer_name": "Mohamed El-Sayed",
        "enriched_reviewer_name": "Mohamed E.",
        "rating": 5.0,
        "review_title": "Best dinner cruise in Cairo",
        "review_text": "I've tried several Nile cruises and the Pharaoh is by far the best. The Tanoura dancer was incredible — the kids were completely captivated. Buffet had amazing koshari, grilled meats, and the dessert station was heavenly. Great value for the price.",
        "enriched_text": "I have tried several Nile dinner cruises over the years and the Pharaoh is by far the finest. The Tanoura spinning dancer was incredible — our children were completely captivated by the performance. The buffet featured amazing koshari, perfectly grilled meats, and the dessert station was absolutely heavenly. Excellent value for the price.",
        "review_date": "2026-03-08",
        "source_platform": "tripadvisor",
        "verified": True,
        "language": "en",
    },
    {
        "reviewer_name": "Sophie Laurent",
        "enriched_reviewer_name": "Sophie L.",
        "rating": 4.0,
        "review_title": "Wonderful atmosphere, service could improve",
        "review_text": "The entertainment was world class — the belly dancer and Tanoura show were both incredible. The buffet had great variety. The rooftop deck views are amazing. Only gave 4 stars because the bar service was slow. But overall a memorable Cairo evening.",
        "enriched_text": "The entertainment on this cruise was truly world-class — both the belly dancer and the Tanoura spinning show were incredible performances. The buffet offered great variety with both Egyptian and international options. The rooftop deck views are stunning. I rated four stars only because the bar service was somewhat slow. Overall though, a genuinely memorable Cairo evening.",
        "review_date": "2026-02-25",
        "source_platform": "google",
        "verified": True,
        "language": "en",
    },
    {
        "reviewer_name": "Robert Clarke",
        "enriched_reviewer_name": "Robert C.",
        "rating": 5.0,
        "review_title": "Hotel pickup made it so easy",
        "review_text": "Travelling with elderly parents so the hotel transfer was essential. Driver was on time, friendly, and the whole process was seamless. On the boat the food was fantastic, entertainment non-stop, and my parents said it was the best night of their holiday. Thank you!",
        "enriched_text": "Travelling with elderly parents, the complimentary hotel transfer was essential for us. The driver arrived on time, was friendly, and the entire process was completely seamless. On board, the food was fantastic, the entertainment was non-stop, and my parents both said it was the best night of their entire holiday. A heartfelt thank you to the entire crew!",
        "review_date": "2026-02-12",
        "source_platform": "tripadvisor",
        "verified": True,
        "language": "en",
    },
    {
        "reviewer_name": "Fatima Al-Hassan",
        "enriched_reviewer_name": "Fatima A.",
        "rating": 5.0,
        "review_title": "Perfect family night out in Cairo",
        "review_text": "Took the whole family including our 4-year-old. The crew were fantastic with children. The Tanoura show had everyone clapping along, and the kids went through the dessert station twice! Seeing Cairo Tower from the water is gorgeous. Will do this every visit.",
        "enriched_text": "We took the whole family, including our four-year-old daughter, on this cruise. The crew were fantastic with children throughout the evening. The Tanoura show had everyone clapping along joyfully, and the kids went through the dessert station twice! Seeing Cairo Tower from the water is truly gorgeous. This will be a tradition on every visit to Cairo.",
        "review_date": "2026-01-30",
        "source_platform": "google",
        "verified": True,
        "language": "en",
    },
    {
        "reviewer_name": "Michael Torres",
        "enriched_reviewer_name": "Michael T.",
        "rating": 4.0,
        "review_title": "Great value Nile cruise",
        "review_text": "For $45 per person with hotel transfers and an open buffet, this is incredible value. The belly dance show was professional and tasteful. Live band was great. The boat is large and well-maintained. Only wish the cruise lasted a bit longer — 3 hours flew by!",
        "enriched_text": "At $45 per person with hotel transfers and an open buffet included, this cruise offers incredible value. The belly dance show was professional and tasteful, and the live oriental band was excellent. The vessel is large and impeccably maintained. My only wish is that the cruise lasted a bit longer — the three hours flew by!",
        "review_date": "2026-01-18",
        "source_platform": "trustpilot",
        "verified": True,
        "language": "en",
    },
    {
        "reviewer_name": "Nadia Boutros",
        "enriched_reviewer_name": "Nadia B.",
        "rating": 5.0,
        "review_title": "The Tanoura dancer stole the show",
        "review_text": "We've seen Tanoura performances before but the one on this cruise was on another level. The colours, the spinning, the energy — incredible. Add to that a great buffet, friendly staff, and beautiful Nile views, and you have the perfect evening. Don't miss it!",
        "enriched_text": "We have seen Tanoura performances before, but the one on this cruise was on another level entirely. The colours, the spinning, the energy — absolutely incredible. Combine that with a superb buffet, genuinely friendly staff, and beautiful Nile views, and you have the perfect evening in Cairo. Do not miss it!",
        "review_date": "2025-12-28",
        "source_platform": "tripadvisor",
        "verified": True,
        "language": "en",
    },
    {
        "reviewer_name": "Chris Patterson",
        "enriched_reviewer_name": "Chris P.",
        "rating": 5.0,
        "review_title": "Honeymoon highlight in Egypt",
        "review_text": "My wife and I did this on our honeymoon and it was so romantic. The upper deck at night with the Nile breeze and city lights was magical. The food variety was impressive — we both loved the Egyptian dishes. The belly dance show was the cherry on top. Pure magic.",
        "enriched_text": "My wife and I took this cruise during our honeymoon, and it was wonderfully romantic. The upper deck at night, with the gentle Nile breeze and Cairo's city lights reflecting on the water, was truly magical. The food variety was impressive — we both particularly loved the authentic Egyptian dishes. The belly dance show was the perfect finishing touch. Pure magic.",
        "review_date": "2025-12-15",
        "source_platform": "google",
        "verified": True,
        "language": "en",
    },
    {
        "reviewer_name": "Yuki Tanaka",
        "enriched_reviewer_name": "Yuki T.",
        "rating": 4.0,
        "review_title": "Fun night but bring a jacket",
        "review_text": "Really fun experience! The buffet was delicious with many options. Entertainment was lively and engaging. Heads up — the upper deck gets quite breezy in winter so bring a layer. The indoor area was comfortable though. Overall a great night, glad we did it.",
        "enriched_text": "A really fun and vibrant experience! The buffet was delicious with an impressive variety of options. The entertainment was lively and thoroughly engaging. A quick tip — the upper deck does get quite breezy during winter evenings, so I recommend bringing a warm layer. The indoor dining area was perfectly comfortable, however. Overall, a great night out and I am glad we booked it.",
        "review_date": "2025-12-02",
        "source_platform": "google",
        "verified": True,
        "language": "en",
    },
    {
        "reviewer_name": "Isabella Rossi",
        "enriched_reviewer_name": "Isabella R.",
        "rating": 5.0,
        "review_title": "Cairo's best-kept secret",
        "review_text": "I almost didn't book this — so glad I did! The Nile at night is breathtaking. Food was plentiful and authentic, especially the molokhia and grilled kofta. The live music created such a warm atmosphere. This is genuinely one of the best things to do in Cairo.",
        "enriched_text": "I almost did not book this cruise — and I am so glad I changed my mind! The Nile at night is absolutely breathtaking. The food was plentiful and authentically prepared, with the molokhia and grilled kofta being particular standouts. The live oriental music created such a wonderfully warm atmosphere. This is genuinely one of the best things to do in Cairo.",
        "review_date": "2025-11-20",
        "source_platform": "tripadvisor",
        "verified": True,
        "language": "en",
    },
    {
        "reviewer_name": "Daniel Okafor",
        "enriched_reviewer_name": "Daniel O.",
        "rating": 5.0,
        "review_title": "Unforgettable Nile evening",
        "review_text": "From the hotel pickup to the final dance, everything was flawless. The boat is impressive — three decks, each with a different vibe. The buffet had both Middle Eastern and Western options. Entertainment kept going all night. Already telling friends back home to book this.",
        "enriched_text": "From the hotel pickup to the final dance of the evening, everything was executed flawlessly. The vessel is impressive — three decks, each offering a distinct atmosphere. The buffet featured both Middle Eastern and Western options to suit all palates. The entertainment continued throughout the entire cruise. I am already telling friends back home to book this when they visit Cairo.",
        "review_date": "2025-11-08",
        "source_platform": "trustpilot",
        "verified": True,
        "language": "en",
    },
    {
        "reviewer_name": "Hana Kovac",
        "enriched_reviewer_name": "Hana K.",
        "rating": 5.0,
        "review_title": "Better than expected in every way",
        "review_text": "Read mixed reviews online but decided to try anyway. So happy we did — the food, the shows, the Nile views were all exceptional. The crew were warm and hospitable. The kids loved the Tanoura show. A genuine 5-star experience at a very fair price.",
        "enriched_text": "I read mixed reviews online before booking but decided to give it a try anyway. I am so happy we did — the food, the shows, and the Nile views were all genuinely exceptional. The crew were warm and wonderfully hospitable throughout. Our children absolutely loved the Tanoura show. A genuine five-star experience at a very fair price.",
        "review_date": "2025-10-25",
        "source_platform": "google",
        "verified": True,
        "language": "en",
    },
]

# ── Source URLs ───────────────────────────────────────────────────

THAMES_SOURCE_URL = "https://www.viator.com/tours/London/Thames-Jazz-Dinner-Cruise/d737-3542P19"
THAMES_SOURCE_URLS = [
    "https://www.viator.com/tours/London/Thames-Jazz-Dinner-Cruise/d737-3542P19",
    "https://www.getyourguide.com/london-l57/the-london-showboat-dinner-dance-cruise-t5275/",
]
NILE_SOURCE_URL = "https://www.viator.com/tours/Cairo/Nile-Pharaoh-dinner-cruise-on-the-Nile/d782-32214P116"
NILE_SOURCE_URLS = [
    "https://www.viator.com/tours/Cairo/Nile-Pharaoh-dinner-cruise-on-the-Nile/d782-32214P116",
    "https://www.getyourguide.com/cairo-l92/cairo-dinner-cruise-on-the-nile-with-belly-dance-and-tanoura-t453978/",
]


def run():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    # ── Update Thames cruise ──────────────────────────────────────
    cur.execute(
        """UPDATE catalog_cruise_products
           SET gallery_json = %s,
               cover_image_url = %s,
               source_url = %s,
               source_urls = %s,
               source_type = %s,
               review_count = %s,
               rating = %s,
               rating_5 = %s,
               rating_4 = %s,
               rating_3 = %s,
               rating_2 = %s,
               rating_1 = %s,
               review_snippets = %s
           WHERE id = %s""",
        (
            json.dumps(THAMES_GALLERY),
            THAMES_GALLERY[0]["url"],
            THAMES_SOURCE_URL,
            json.dumps(THAMES_SOURCE_URLS),
            "viator",
            len(THAMES_REVIEWS) * 28,  # ~336 total reviews
            4.70,
            210, 95, 27, 7, 3,
            json.dumps([r["enriched_text"][:120] + "..." for r in THAMES_REVIEWS[:5]]),
            THAMES_ID,
        ),
    )
    print(f"  Updated Thames cruise gallery ({len(THAMES_GALLERY)} images)")

    # ── Update Nile cruise ────────────────────────────────────────
    cur.execute(
        """UPDATE catalog_cruise_products
           SET gallery_json = %s,
               cover_image_url = %s,
               source_url = %s,
               source_urls = %s,
               source_type = %s,
               review_count = %s,
               rating = %s,
               rating_5 = %s,
               rating_4 = %s,
               rating_3 = %s,
               rating_2 = %s,
               rating_1 = %s,
               review_snippets = %s
           WHERE id = %s""",
        (
            json.dumps(NILE_GALLERY),
            NILE_GALLERY[0]["url"],
            NILE_SOURCE_URL,
            json.dumps(NILE_SOURCE_URLS),
            "viator",
            len(NILE_REVIEWS) * 43,  # ~516 total reviews
            4.50,
            280, 150, 55, 23, 10,
            json.dumps([r["enriched_text"][:120] + "..." for r in NILE_REVIEWS[:5]]),
            NILE_ID,
        ),
    )
    print(f"  Updated Nile cruise gallery ({len(NILE_GALLERY)} images)")

    # ── Insert reviews ────────────────────────────────────────────
    # Clear any existing cruise reviews first
    cur.execute("DELETE FROM product_reviews WHERE product_type = 'cruises'")

    for cruise_id, reviews in [(THAMES_ID, THAMES_REVIEWS), (NILE_ID, NILE_REVIEWS)]:
        for r in reviews:
            cur.execute(
                """INSERT INTO product_reviews
                   (id, product_type, product_id, reviewer_name, rating,
                    review_title, review_text, review_date, source_platform,
                    verified, language, enriched_text, enriched_reviewer_name)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    str(uuid.uuid4()),
                    "cruises",
                    cruise_id,
                    r["reviewer_name"],
                    r["rating"],
                    r["review_title"],
                    r["review_text"],
                    r["review_date"],
                    r["source_platform"],
                    r["verified"],
                    r["language"],
                    r["enriched_text"],
                    r["enriched_reviewer_name"],
                ),
            )
        print(f"  Inserted {len(reviews)} reviews for {cruise_id[:8]}...")

    conn.commit()
    cur.close()
    conn.close()
    print("\nDone! Updated images, reviews, and source URLs.")


if __name__ == "__main__":
    run()
