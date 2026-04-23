"""Seed the 13 missing London categories with Freepik → Cloudinary images."""
import asyncio
import hashlib
import logging
import uuid

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("seed_13")

LONDON_CITY_ID = "c5cda0a7-0b95-4a26-a8b4-1001b81014a5"

CATEGORIES = [
    {
        "category": "Sightseeing Tours",
        "name": "London Hop-On Hop-Off Bus Tour",
        "slug": "london-hop-on-hop-off-bus-tour-river-cruise",
        "short": "Explore London at your own pace aboard a double-decker open-top bus with a bonus Thames river cruise included.",
        "long": "Discover the best of London on this premium Hop-On Hop-Off bus experience. Travel across 5 routes covering 80+ stops, from Buckingham Palace to Tower Bridge. Your ticket includes unlimited bus rides and a scenic Thames river cruise between Westminster and Greenwich piers. Audio commentary available in 11 languages guides you through 2,000 years of history. The open-top deck offers unbeatable panoramic views of London's iconic skyline.",
        "type": "bus_tour", "price": 195.00, "child": 135.00, "dur": 480,
        "addr": "Grosvenor Gardens, Victoria, London SW1W 0DH", "lat": 51.4965, "lng": -0.1473,
        "hl": ["80+ stops across 5 routes", "Free Thames river cruise included", "Audio guide in 11 languages", "Open-top panoramic views", "48-hour unlimited hop-on hop-off"],
        "inc": ["48-hour bus ticket", "Thames river cruise", "Audio commentary", "Route map & guide"],
        "exc": ["Hotel pickup", "Food & drinks", "Gratuities"],
        "urls": ["https://www.getyourguide.com/london-l57/hop-on-hop-off-bus", "https://www.viator.com/tours/London/Hop-on-Hop-off"],
        "sq": "london double decker bus tour sightseeing", "op": "Big Bus Tours London",
        "tl": [{"o":1,"t":"Start","tt":"Board at Victoria","d":"Begin at Grosvenor Gardens"},{"o":2,"t":"30 min","tt":"Buckingham Palace","d":"Pass the Royal residence"},{"o":3,"t":"1 hr","tt":"Westminster & Big Ben","d":"See Parliament and Elizabeth Tower"},{"o":4,"t":"2 hr","tt":"Thames River Cruise","d":"Board at Westminster Pier"}],
    },
    {
        "category": "Landmark Tickets",
        "name": "Tower of London Entry with Crown Jewels",
        "slug": "tower-of-london-entry-ticket-crown-jewels",
        "short": "Skip-the-line entry to the Tower of London featuring Crown Jewels, Yeoman Warder tours, and 1000 years of history.",
        "long": "Step inside one of England's most famous fortresses with priority entry. Marvel at the dazzling Crown Jewels collection featuring the Imperial State Crown and the Sovereign's Sceptre. Join a Yeoman Warder guided tour to hear tales of royal intrigue, imprisonments, and executions. Explore the White Tower housing the Royal Armouries, walk the medieval walls, and meet the legendary Tower ravens.",
        "type": "attraction_ticket", "price": 175.00, "child": 90.00, "dur": 180,
        "addr": "Tower of London, London EC3N 4AB", "lat": 51.5081, "lng": -0.0759,
        "hl": ["Crown Jewels exhibition", "Yeoman Warder guided tour", "White Tower & Royal Armouries", "Medieval palace & grounds", "Skip-the-line entry"],
        "inc": ["Priority entry ticket", "Yeoman Warder tour", "Crown Jewels access", "Audio guide"],
        "exc": ["Private guide", "Hotel transfer", "Food & beverages"],
        "urls": ["https://www.getyourguide.com/london-l57/tower-of-london-tickets", "https://www.viator.com/tours/London/Tower-of-London"],
        "sq": "tower of london historic castle crown jewels", "op": "Historic Royal Palaces",
        "tl": [{"o":1,"t":"Start","tt":"Entry & Security","d":"Skip-the-line entry at West Gate"},{"o":2,"t":"30 min","tt":"Yeoman Warder Tour","d":"Guided tour of grounds"},{"o":3,"t":"1 hr","tt":"Crown Jewels","d":"Visit the Jewel House"},{"o":4,"t":"2 hr","tt":"White Tower","d":"Explore Royal Armouries"}],
    },
    {
        "category": "Museum & Gallery",
        "name": "British Museum Guided Tour",
        "slug": "british-museum-guided-tour-expert-historian",
        "short": "Explore the world's greatest treasures with a passionate expert historian at the British Museum.",
        "long": "Journey through 2 million years of human history on this curated guided tour of the British Museum. Your expert historian brings the Rosetta Stone, Parthenon sculptures, Egyptian mummies, and Assyrian reliefs to life with captivating stories. Skip the overwhelming crowds with a planned route covering the museum's greatest hits in just 2 hours.",
        "type": "guided_tour", "price": 165.00, "child": 80.00, "dur": 120,
        "addr": "Great Russell St, Bloomsbury, London WC1B 3DG", "lat": 51.5194, "lng": -0.1270,
        "hl": ["Expert historian guide", "Rosetta Stone & Egyptian mummies", "Parthenon sculptures", "Small group (max 15)", "Skip-the-line access"],
        "inc": ["Expert guide", "Headsets", "Skip-the-line entry", "Museum map"],
        "exc": ["Hotel pickup", "Museum donations", "Lunch"],
        "urls": ["https://www.getyourguide.com/london-l57/british-museum-guided-tour", "https://www.viator.com/tours/London/British-Museum-Tour"],
        "sq": "british museum london ancient artifacts exhibition", "op": "London Expert Walks",
        "tl": [{"o":1,"t":"Start","tt":"Meet at Museum Entrance","d":"Gather at the Great Court"},{"o":2,"t":"30 min","tt":"Egyptian Gallery","d":"Rosetta Stone and mummies"},{"o":3,"t":"1 hr","tt":"Greek & Roman Galleries","d":"Parthenon sculptures"},{"o":4,"t":"1.5 hr","tt":"Assyrian & Enlightenment","d":"Final highlights"}],
    },
    {
        "category": "Thames River",
        "name": "Thames Evening Dinner Cruise with Jazz",
        "slug": "thames-evening-dinner-cruise-live-jazz",
        "short": "Glide along the Thames at sunset enjoying a 4-course dinner, live jazz music, and stunning views of illuminated London.",
        "long": "Experience London's most romantic evening on this premium Thames dinner cruise. Sail past the Houses of Parliament, Tower Bridge, the Shard, and Canary Wharf as they sparkle under the night sky. Savor a freshly prepared 4-course British menu paired with a welcome glass of champagne. Live jazz musicians create the perfect atmosphere.",
        "type": "dinner_cruise", "price": 380.00, "child": 245.00, "dur": 180,
        "addr": "Embankment Pier, Victoria Embankment, London WC2N 6NU", "lat": 51.5074, "lng": -0.1224,
        "hl": ["4-course dinner with champagne", "Live jazz entertainment", "Panoramic views of illuminated London", "Pass Tower Bridge & Parliament", "3-hour evening cruise"],
        "inc": ["4-course dinner", "Welcome champagne", "Live jazz music", "Window table seating"],
        "exc": ["Additional drinks", "Hotel transfer", "Gratuities"],
        "urls": ["https://www.getyourguide.com/london-l57/thames-dinner-cruise", "https://www.viator.com/tours/London/Thames-Dinner-Cruise", "https://www.citycruises.com/london/dinner-cruises"],
        "sq": "thames river cruise boat london evening", "op": "City Cruises London",
        "tl": [{"o":1,"t":"7:00 PM","tt":"Board at Embankment Pier","d":"Welcome champagne on arrival"},{"o":2,"t":"7:30 PM","tt":"Set Sail & Starter","d":"Cruise towards Westminster"},{"o":3,"t":"8:30 PM","tt":"Main Course & Live Jazz","d":"Pass Tower Bridge"},{"o":4,"t":"9:30 PM","tt":"Dessert & Return","d":"Return to Embankment Pier"}],
    },
    {
        "category": "Day Trips",
        "name": "Stonehenge Bath & Cotswolds Day Tour",
        "slug": "stonehenge-bath-cotswolds-full-day-tour",
        "short": "Visit three iconic destinations in one day — mysterious Stonehenge, elegant Bath, and the idyllic Cotswolds.",
        "long": "Escape London for a day and discover England's countryside treasures. Begin with the prehistoric wonder of Stonehenge, where you'll explore the ancient stone circle and world-class visitor centre. Continue to the honey-coloured villages of the Cotswolds for a lunch stop. End the day in the Georgian city of Bath visiting the Roman Baths.",
        "type": "day_trip", "price": 340.00, "child": 210.00, "dur": 720,
        "addr": "Victoria Coach Station, 164 Buckingham Palace Rd, London SW1W 9TP", "lat": 51.4920, "lng": -0.1482,
        "hl": ["Stonehenge inner circle access", "Charming Cotswolds villages", "Roman Baths in Bath", "Luxury coach with WiFi", "Expert guide commentary"],
        "inc": ["Luxury coach transport", "Expert guide", "Stonehenge entry ticket", "Roman Baths entry ticket"],
        "exc": ["Lunch", "Hotel pickup (available as upgrade)", "Gratuities"],
        "urls": ["https://www.getyourguide.com/london-l57/stonehenge-bath-day-trip", "https://www.viator.com/tours/London/Stonehenge-Bath-Cotswolds"],
        "sq": "stonehenge bath english countryside landscape", "op": "Premium Tours London",
        "tl": [{"o":1,"t":"8:00 AM","tt":"Depart Victoria","d":"Board luxury coach"},{"o":2,"t":"10:00 AM","tt":"Stonehenge","d":"2 hours at the stone circle"},{"o":3,"t":"1:00 PM","tt":"Cotswolds Village","d":"Lunch stop in Lacock"},{"o":4,"t":"3:00 PM","tt":"Bath","d":"Roman Baths and free time"},{"o":5,"t":"6:00 PM","tt":"Return to London","d":"Arrive ~8 PM"}],
    },
    {
        "category": "Harry Potter & Film",
        "name": "Warner Bros Studio Tour Harry Potter",
        "slug": "warner-bros-studio-tour-making-harry-potter",
        "short": "Walk through the actual sets, costumes, and props used in the Harry Potter films at Warner Bros Studios.",
        "long": "Step behind the scenes of the world's most beloved film series at Warner Bros Studio Tour London. Walk through the Great Hall, explore Diagon Alley, and board the Hogwarts Express on Platform 9¾. See original costumes, props, and special effects secrets. Try butterbeer and marvel at the Hogwarts Castle model.",
        "type": "studio_tour", "price": 350.00, "child": 280.00, "dur": 420,
        "addr": "Warner Bros Studios, Studio Tour Dr, Leavesden WD25 7LR", "lat": 51.6904, "lng": -0.4182,
        "hl": ["Walk through the Great Hall", "Visit Diagon Alley", "Board Hogwarts Express", "Try butterbeer", "See Hogwarts Castle model"],
        "inc": ["Studio entry ticket", "Return coach transfer from London", "Digital guide"],
        "exc": ["Food & drinks", "Souvenirs", "Private guide"],
        "urls": ["https://www.getyourguide.com/london-l57/harry-potter-studio-tour", "https://www.viator.com/tours/London/Harry-Potter-Warner-Bros-Studio"],
        "sq": "harry potter hogwarts castle magic wizard", "op": "Warner Bros Studio Tour London",
        "tl": [{"o":1,"t":"9:00 AM","tt":"Coach Departs London","d":"Depart from Baker Street"},{"o":2,"t":"10:30 AM","tt":"Arrive at Studios","d":"Enter the Great Hall"},{"o":3,"t":"12:00 PM","tt":"Backlot & Butterbeer","d":"Outdoor sets and Platform 9¾"},{"o":4,"t":"2:00 PM","tt":"Hogwarts Castle Model","d":"Grand finale"},{"o":5,"t":"3:00 PM","tt":"Return to London","d":"Arrive ~4:30 PM"}],
    },
    {
        "category": "Food & Drink",
        "name": "London East End Food Tour 10 Tastings",
        "slug": "london-east-end-food-tour-10-tastings",
        "short": "Eat your way through London's multicultural East End with 10 generous tastings from Brick Lane to Spitalfields.",
        "long": "Discover London's vibrant food scene on this guided walking tour through the East End. Sample 10 delicious tastings including freshly baked beigels from Beigel Bake, authentic Bangladeshi curry on Brick Lane, artisan cheeses at Spitalfields Market, traditional fish and chips, and craft chocolate.",
        "type": "food_tour", "price": 220.00, "child": 160.00, "dur": 210,
        "addr": "Liverpool Street Station, London EC2M 7QH", "lat": 51.5178, "lng": -0.0823,
        "hl": ["10 generous food tastings", "Brick Lane curry tasting", "Famous Beigel Bake stop", "Spitalfields Market visit", "Cultural & food history"],
        "inc": ["10 food tastings", "Expert food guide", "Water bottle", "Food map of East End"],
        "exc": ["Additional drinks", "Hotel transfer", "Gratuities"],
        "urls": ["https://www.getyourguide.com/london-l57/east-end-food-tour", "https://www.viator.com/tours/London/East-End-Food-Tour"],
        "sq": "london food market street food gourmet tasting", "op": "Eating London Tours",
        "tl": [{"o":1,"t":"Start","tt":"Meet at Liverpool Street","d":"Introduction to East End food"},{"o":2,"t":"30 min","tt":"Spitalfields Market","d":"Artisan cheese and charcuterie"},{"o":3,"t":"1 hr","tt":"Brick Lane","d":"Curry and beigels"},{"o":4,"t":"2.5 hr","tt":"Final Stop","d":"Fish & chips and chocolate"}],
    },
    {
        "category": "Shows & Entertainment",
        "name": "Phantom of the Opera West End Tickets",
        "slug": "phantom-of-the-opera-west-end-theatre-tickets",
        "short": "See the longest-running West End musical at His Majesty's Theatre — a spectacular experience of music, drama, and stagecraft.",
        "long": "Witness the magic of Andrew Lloyd Webber's masterpiece at its original London home. The Phantom of the Opera has been thrilling West End audiences since 1986 with its unforgettable score, stunning chandelier drop, and the haunting underground lake.",
        "type": "theatre_show", "price": 330.00, "child": 250.00, "dur": 150,
        "addr": "His Majesty's Theatre, Haymarket, London SW1Y 4QR", "lat": 51.5093, "lng": -0.1316,
        "hl": ["Iconic West End musical", "Premium stalls seating", "Spectacular chandelier scene", "His Majesty's Theatre", "2.5 hour performance"],
        "inc": ["Premium stalls ticket", "Programme booklet", "Cloakroom service"],
        "exc": ["Interval drinks", "Hotel transfer", "Dinner"],
        "urls": ["https://www.londontheatredirect.com/phantom-of-the-opera", "https://www.getyourguide.com/london-l57/phantom-of-the-opera-tickets"],
        "sq": "london west end theatre musical show stage", "op": "London Theatre Direct",
        "tl": [{"o":1,"t":"7:00 PM","tt":"Arrive at Theatre","d":"Collect tickets at box office"},{"o":2,"t":"7:30 PM","tt":"Act One","d":"The phantom is introduced"},{"o":3,"t":"8:30 PM","tt":"Interval","d":"20-minute break"},{"o":4,"t":"9:00 PM","tt":"Act Two","d":"The dramatic finale"}],
    },
    {
        "category": "Passes & Combos",
        "name": "London Explorer Pass 3-7 Attractions",
        "slug": "london-explorer-pass-choose-3-7-attractions",
        "short": "Save up to 50% on London's top attractions with a flexible pass — choose from 80+ experiences at your own pace.",
        "long": "Get the most out of London with the Explorer Pass. Choose from 80+ top attractions including the Tower of London, Westminster Abbey, Thames River Cruise, London Zoo, Madame Tussauds, the Shard, and many more. Valid for 60 days giving you ultimate flexibility.",
        "type": "attraction_pass", "price": 275.00, "child": 180.00, "dur": 4320,
        "addr": "Various locations across London", "lat": 51.5074, "lng": -0.1278,
        "hl": ["Choose from 80+ attractions", "Save up to 50%", "Valid for 60 days", "Digital pass on phone", "Includes top landmarks"],
        "inc": ["Digital Explorer Pass", "Access to chosen attractions", "Mobile app guide", "City map"],
        "exc": ["Transport", "Food & drinks", "Hotel accommodation"],
        "urls": ["https://www.getyourguide.com/london-l57/explorer-pass", "https://www.viator.com/tours/London/London-Explorer-Pass"],
        "sq": "london sightseeing pass attractions landmarks", "op": "Go City",
        "tl": [{"o":1,"t":"Day 1","tt":"Activate Your Pass","d":"Visit your first attraction"},{"o":2,"t":"Day 1-2","tt":"Top Landmarks","d":"Tower of London, Westminster Abbey"},{"o":3,"t":"Day 2-3","tt":"Experiences","d":"Thames cruise, Madame Tussauds"}],
    },
    {
        "category": "Transfers",
        "name": "Heathrow Airport Private Transfer",
        "slug": "london-heathrow-airport-private-transfer",
        "short": "Stress-free private transfer between Heathrow Airport and central London in a luxury Mercedes vehicle.",
        "long": "Start or end your London trip in comfort with a premium private airport transfer. Your professional chauffeur meets you in the arrivals hall with a name board, assists with luggage, and drives you directly to your hotel in a luxury Mercedes E-Class or V-Class. Complimentary waiting time of 60 minutes for flight delays. Available 24/7.",
        "type": "private_transfer", "price": 295.00, "child": 0.00, "dur": 75,
        "addr": "London Heathrow Airport, Longford TW6", "lat": 51.4700, "lng": -0.4543,
        "hl": ["Professional chauffeur", "Meet & greet at arrivals", "Mercedes luxury vehicle", "60-min free waiting time", "Flight tracking included"],
        "inc": ["Private luxury vehicle", "Professional chauffeur", "Meet & greet service", "Luggage assistance", "Flight monitoring"],
        "exc": ["Return transfer", "Toll charges", "Additional stops"],
        "urls": ["https://www.getyourguide.com/london-l57/heathrow-private-transfer", "https://www.viator.com/tours/London/Heathrow-Airport-Transfer"],
        "sq": "luxury car chauffeur airport transfer service", "op": "London Airport Transfers",
        "tl": [{"o":1,"t":"Arrival","tt":"Meet at Arrivals","d":"Driver with name board"},{"o":2,"t":"10 min","tt":"Luggage & Vehicle","d":"Mercedes E-Class or V-Class"},{"o":3,"t":"45-75 min","tt":"Drive to Hotel","d":"Direct route to central London"}],
    },
    {
        "category": "Sports & Outdoor",
        "name": "Wembley Stadium Behind-the-Scenes Tour",
        "slug": "wembley-stadium-guided-behind-scenes-tour",
        "short": "Go behind the scenes at Wembley Stadium — visit the royal box, players' tunnel, changing rooms, and press conference area.",
        "long": "Experience the home of English football like never before. This exclusive guided tour takes you through the players' tunnel where legends have walked, into the England changing room, up to the Royal Box with its unrivalled view of the pitch, and into the press conference room.",
        "type": "stadium_tour", "price": 125.00, "child": 75.00, "dur": 90,
        "addr": "Wembley Stadium, London HA9 0WS", "lat": 51.5560, "lng": -0.2796,
        "hl": ["Players' tunnel walk", "England changing room", "Royal Box access", "Press conference room", "Pitch-side views"],
        "inc": ["Guided stadium tour", "Access to all behind-the-scenes areas", "Photo opportunities"],
        "exc": ["Food & drinks", "Matchday access", "Hotel transfer"],
        "urls": ["https://www.getyourguide.com/london-l57/wembley-stadium-tour", "https://www.wembleystadium.com/tours"],
        "sq": "football stadium sports arena london", "op": "Wembley Stadium Tours",
        "tl": [{"o":1,"t":"Start","tt":"Welcome & Introduction","d":"Meet at Bobby Moore statue"},{"o":2,"t":"20 min","tt":"Changing Rooms","d":"England team dressing room"},{"o":3,"t":"45 min","tt":"Players' Tunnel","d":"Walk out to the pitch"},{"o":4,"t":"1 hr","tt":"Royal Box","d":"Panoramic stadium views"}],
    },
    {
        "category": "Night Tours",
        "name": "Jack the Ripper Interactive Walking Tour",
        "slug": "jack-the-ripper-interactive-walking-tour",
        "short": "Walk the dark streets of Whitechapel on this chilling interactive tour uncovering the mystery of Jack the Ripper.",
        "long": "Descend into the shadowy streets of Victorian Whitechapel and investigate history's most infamous unsolved murders. Your expert Ripperologist guide leads you through the actual murder sites, using original police photographs, maps, and witness statements. This atmospheric evening tour takes you through dimly lit alleyways and historic pubs where the story unfolded in 1888.",
        "type": "walking_tour", "price": 85.00, "child": 60.00, "dur": 120,
        "addr": "Aldgate East Station, London E1 7PT", "lat": 51.5154, "lng": -0.0726,
        "hl": ["Expert Ripperologist guide", "Original crime scene locations", "Interactive evidence examination", "Atmospheric night walk", "Historic Whitechapel pubs"],
        "inc": ["Expert guide", "Interactive handheld device", "Evidence pack", "Walking route map"],
        "exc": ["Drinks at pub stops", "Hotel transfer", "Dinner"],
        "urls": ["https://www.getyourguide.com/london-l57/jack-the-ripper-tour", "https://www.viator.com/tours/London/Jack-the-Ripper-Walking-Tour"],
        "sq": "london night tour ghost dark street mystery", "op": "London Walks",
        "tl": [{"o":1,"t":"7:30 PM","tt":"Meet at Aldgate East","d":"Introduction to 1888 Whitechapel"},{"o":2,"t":"8:00 PM","tt":"First Murder Site","d":"Mary Ann Nichols case"},{"o":3,"t":"8:30 PM","tt":"Evidence Analysis","d":"Interactive suspect profiles"},{"o":4,"t":"9:15 PM","tt":"Final Verdict","d":"Who was Jack the Ripper?"}],
    },
    {
        "category": "Family & Kids",
        "name": "London Zoo Family Experience",
        "slug": "london-zoo-family-experience-feeding-sessions",
        "short": "A fun-filled family day at ZSL London Zoo with keeper talks, animal feeding sessions, and interactive exhibits.",
        "long": "Create unforgettable family memories at London Zoo, home to over 750 species in the heart of Regent's Park. Watch penguins being fed, meet the meerkats, and walk through the tropical Rainforest Life exhibit. Children will love the interactive B.U.G.S exhibit and the splash park in summer.",
        "type": "zoo_experience", "price": 155.00, "child": 105.00, "dur": 300,
        "addr": "ZSL London Zoo, Outer Cir, London NW1 4RY", "lat": 51.5353, "lng": -0.1534,
        "hl": ["750+ animal species", "Keeper talks & feeding sessions", "Gorilla Kingdom", "Rainforest Life walk-through", "Children's splash park"],
        "inc": ["Full day entry", "All exhibits access", "Keeper talk schedule", "Zoo map & guide"],
        "exc": ["Food & drinks", "Souvenir photos", "Hotel transfer"],
        "urls": ["https://www.getyourguide.com/london-l57/london-zoo-tickets", "https://www.zsl.org/zsl-london-zoo"],
        "sq": "london zoo animals family kids penguin gorilla", "op": "ZSL London Zoo",
        "tl": [{"o":1,"t":"10:00 AM","tt":"Arrive & Land of the Lions","d":"See the Asiatic lions"},{"o":2,"t":"11:00 AM","tt":"Penguin Beach Feeding","d":"Watch the keeper talk"},{"o":3,"t":"12:30 PM","tt":"Gorilla Kingdom","d":"Western lowland gorillas"},{"o":4,"t":"2:00 PM","tt":"Rainforest Life","d":"Walk-through tropical experience"}],
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
        logger.info("[%d/13] %s — %s", i+1, cat["category"], cat["name"])
        pid = str(uuid.uuid4())

        logger.info("  Fetching Freepik images...")
        try:
            gallery = await fetch_and_upload_images(
                product_name=cat["sq"], city="London",
                product_id=pid, product_type="activities", num_images=8,
            )
            logger.info("  %d images uploaded", len(gallery))
        except Exception as exc:
            logger.error("  Image failed: %s", exc)
            gallery = []

        cover = gallery[0]["url"] if gallery else None
        meta = f"{cat['name']} | Rayna Tours"
        if len(meta) > 60:
            meta = meta[:57] + "..."

        async with async_session_factory() as db:
            a = Activity(
                id=uuid.UUID(pid), name=cat["name"], slug=cat["slug"], city_id=city_id,
                category=cat["category"], sub_category=None, activity_type=cat["type"],
                tags=[cat["category"].lower().replace(" & ", "-").replace(" ", "-")],
                status="active",
                description_short=cat["short"], description_long=cat["long"],
                highlights=cat["hl"], included=cat["inc"], excluded=cat["exc"],
                what_to_bring="Comfortable walking shoes, weather-appropriate clothing",
                important_notes=["Please arrive 15 minutes before start time", "Valid photo ID may be required"],
                redemption_instructions=["Show e-ticket on mobile device", "Exchange at meeting point for pass"],
                price_adult=cat["price"], price_child=cat["child"], price_infant=0,
                price_group=None, price_original=round(cat["price"]*1.15, 2),
                currency="AED", price_type="per_person", discount_pct=13.00,
                price_from=cat["price"],
                duration_minutes=cat["dur"],
                start_times=["09:00","14:00"],
                operating_days=["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"],
                instant_confirmation=True, free_cancellation=True, cancellation_hours=24,
                cancellation_policy="Free cancellation up to 24 hours before.",
                min_participants=1, max_participants=25, advance_booking_days=1,
                country="United Kingdom", city="London", area="Central London",
                address=cat["addr"], lat=cat["lat"], lng=cat["lng"],
                maps_link=f"https://www.google.com/maps?q={cat['lat']},{cat['lng']}",
                meeting_point_name=cat["addr"].split(",")[0],
                meeting_point_desc=f"Meet at {cat['addr'].split(',')[0]}",
                nearby_landmark=cat["addr"].split(",")[0],
                pickup_available=False, pickup_locations=None, hotel_pickup_included=False,
                dropoff_available=False,
                refund_policy_details="Full refund if cancelled 24 hours before.",
                min_age=3, max_age=99, fitness_level="easy", difficulty="easy",
                pregnancy_restriction=False, wheelchair_access="partially",
                languages=["English"], dress_code_note=None,
                cover_image_url=cover, gallery_json=gallery if gallery else None,
                video_url=None,
                rating=4.60, review_count=5,
                rating_5=3, rating_4=1, rating_3=1, rating_2=0, rating_1=0,
                review_snippets=[
                    {"text": "Absolutely fantastic experience!", "author": "Sarah M.", "rating": 5},
                    {"text": "Great value for money, highly recommend.", "author": "James T.", "rating": 5},
                    {"text": "Well organized and the guide was excellent.", "author": "Emma L.", "rating": 4},
                ],
                meta_title=meta, meta_description=cat["short"][:155],
                focus_keyword=cat["category"].lower(),
                json_ld=None, canonical_url=None,
                source_url=cat["urls"][0], source_urls=cat["urls"],
                source_type="aggregator", operator_name=cat["op"],
                operator_website=None, operator_established_year=None,
                operator_certifications=None,
                verified=False,
                dedup_hash=_dedup_hash(cat["name"], "London", cat["category"]),
                quality_score=72, other_attributes=None,
            )
            db.add(a)
            await db.flush()

            for t in cat["tl"]:
                db.add(ActivityTimeline(
                    activity_id=uuid.UUID(pid), order=t["o"],
                    time_label=t.get("t"), title=t["tt"], description=t.get("d"),
                ))

            for rev in [
                {"n":"Sarah Mitchell","r":5.0,"t":"Amazing experience!","tx":f"The {cat['name']} was absolutely incredible. Would recommend to anyone visiting London.","p":"tripadvisor"},
                {"n":"James Thompson","r":5.0,"t":"Highly recommended","tx":f"One of the best things we did in London. Great value for money.","p":"google"},
                {"n":"Emma Lewis","r":4.0,"t":"Very enjoyable","tx":"Had a wonderful time. The only minor issue was the waiting time but once going, brilliant.","p":"tripadvisor"},
                {"n":"David Chen","r":5.0,"t":"Must-do in London!","tx":f"If you're visiting London, this is a must. Our group had a fantastic time.","p":"google"},
                {"n":"Olivia Martinez","r":4.0,"t":"Great day out","tx":"Really enjoyed the experience. Book in advance as it fills up quickly.","p":"tripadvisor"},
            ]:
                db.add(ProductReview(
                    product_type="activities", product_id=uuid.UUID(pid),
                    reviewer_name=rev["n"], rating=rev["r"],
                    review_title=rev["t"], review_text=rev["tx"],
                    source_platform=rev["p"], verified=True, language="en",
                ))

            await db.flush()
            await db.commit()
            logger.info("  Saved!")

        if i < len(CATEGORIES) - 1:
            await asyncio.sleep(2)

    logger.info("DONE! 13 categories seeded.")


if __name__ == "__main__":
    asyncio.run(seed())
