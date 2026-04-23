"""Seed 15 London activities (1 per category) with REAL Freepik → Cloudinary images.

Usage: python seed_london_real_images.py
"""
import asyncio
import hashlib
import logging
import sys
import uuid
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("seed_london")

LONDON_CITY_ID = "c5cda0a7-0b95-4a26-a8b4-1001b81014a5"

CATEGORIES = [
    {
        "category": "Sightseeing Tours",
        "name": "London Hop-On Hop-Off Bus Tour with River Cruise",
        "slug": "london-hop-on-hop-off-bus-tour-river-cruise",
        "description_short": "Explore London at your own pace aboard a double-decker open-top bus with a bonus Thames river cruise included.",
        "description_long": "Discover the best of London on this premium Hop-On Hop-Off bus experience. Travel across 5 routes covering 80+ stops, from Buckingham Palace to Tower Bridge. Your ticket includes unlimited bus rides and a scenic Thames river cruise between Westminster and Greenwich piers. Audio commentary available in 11 languages guides you through 2,000 years of history. The open-top deck offers unbeatable panoramic views of London's iconic skyline.",
        "activity_type": "bus_tour",
        "price_adult": 195.00,
        "price_child": 135.00,
        "duration_minutes": 480,
        "address": "Grosvenor Gardens, Victoria, London SW1W 0DH",
        "lat": 51.4965, "lng": -0.1473,
        "highlights": ["80+ stops across 5 routes", "Free Thames river cruise included", "Audio guide in 11 languages", "Open-top panoramic views", "48-hour unlimited hop-on hop-off"],
        "included": ["48-hour bus ticket", "Thames river cruise", "Audio commentary", "Route map & guide"],
        "excluded": ["Hotel pickup", "Food & drinks", "Gratuities"],
        "source_urls": ["https://www.getyourguide.com/london-l57/hop-on-hop-off-bus", "https://www.viator.com/tours/London/Hop-on-Hop-off"],
        "search_query": "london double decker bus tour sightseeing",
        "operator_name": "Big Bus Tours London",
        "timeline": [
            {"order": 1, "time_label": "Start", "title": "Board at Victoria", "description": "Begin at Grosvenor Gardens stop"},
            {"order": 2, "time_label": "30 min", "title": "Buckingham Palace", "description": "Pass the Royal residence"},
            {"order": 3, "time_label": "1 hr", "title": "Westminster & Big Ben", "description": "See Parliament and the Elizabeth Tower"},
            {"order": 4, "time_label": "2 hr", "title": "Thames River Cruise", "description": "Board the river cruise at Westminster Pier"},
        ],
    },
    {
        "category": "Landmark Tickets",
        "name": "Tower of London Entry Ticket with Crown Jewels",
        "slug": "tower-of-london-entry-ticket-crown-jewels",
        "description_short": "Skip-the-line entry to the iconic Tower of London featuring the Crown Jewels, Yeoman Warder tours, and 1000 years of history.",
        "description_long": "Step inside one of England's most famous fortresses with priority entry. Marvel at the dazzling Crown Jewels collection featuring the Imperial State Crown and the Sovereign's Sceptre. Join a Yeoman Warder guided tour to hear tales of royal intrigue, imprisonments, and executions. Explore the White Tower housing the Royal Armouries, walk the medieval walls, and meet the legendary Tower ravens.",
        "activity_type": "attraction_ticket",
        "price_adult": 175.00,
        "price_child": 90.00,
        "duration_minutes": 180,
        "address": "Tower of London, London EC3N 4AB",
        "lat": 51.5081, "lng": -0.0759,
        "highlights": ["Crown Jewels exhibition", "Yeoman Warder guided tour", "White Tower & Royal Armouries", "Medieval palace & grounds", "Skip-the-line entry"],
        "included": ["Priority entry ticket", "Yeoman Warder tour", "Crown Jewels access", "Audio guide"],
        "excluded": ["Private guide", "Hotel transfer", "Food & beverages"],
        "source_urls": ["https://www.getyourguide.com/london-l57/tower-of-london-tickets", "https://www.viator.com/tours/London/Tower-of-London"],
        "search_query": "tower of london crown jewels landmark",
        "operator_name": "Historic Royal Palaces",
        "timeline": [
            {"order": 1, "time_label": "Start", "title": "Entry & Security", "description": "Skip-the-line entry at the West Gate"},
            {"order": 2, "time_label": "30 min", "title": "Yeoman Warder Tour", "description": "Guided tour of the grounds"},
            {"order": 3, "time_label": "1 hr", "title": "Crown Jewels", "description": "Visit the Jewel House"},
            {"order": 4, "time_label": "2 hr", "title": "White Tower", "description": "Explore the Royal Armouries"},
        ],
    },
    {
        "category": "Museum & Gallery",
        "name": "British Museum Guided Tour with Expert Historian",
        "slug": "british-museum-guided-tour-expert-historian",
        "description_short": "Explore the world's greatest treasures with a passionate expert historian at the British Museum.",
        "description_long": "Journey through 2 million years of human history on this curated guided tour of the British Museum. Your expert historian brings the Rosetta Stone, Parthenon sculptures, Egyptian mummies, and Assyrian reliefs to life with captivating stories. Skip the overwhelming crowds with a planned route covering the museum's greatest hits in just 2 hours. Small group size ensures a personal, intimate experience.",
        "activity_type": "guided_tour",
        "price_adult": 165.00,
        "price_child": 80.00,
        "duration_minutes": 120,
        "address": "Great Russell St, Bloomsbury, London WC1B 3DG",
        "lat": 51.5194, "lng": -0.1270,
        "highlights": ["Expert historian guide", "Rosetta Stone & Egyptian mummies", "Parthenon sculptures", "Small group (max 15)", "Skip-the-line access"],
        "included": ["Expert guide", "Headsets", "Skip-the-line entry", "Museum map"],
        "excluded": ["Hotel pickup", "Museum donations", "Lunch"],
        "source_urls": ["https://www.getyourguide.com/london-l57/british-museum-guided-tour", "https://www.viator.com/tours/London/British-Museum-Tour"],
        "search_query": "british museum london ancient artifacts exhibition",
        "operator_name": "London Expert Walks",
        "timeline": [
            {"order": 1, "time_label": "Start", "title": "Meet at Museum Entrance", "description": "Gather at the Great Court"},
            {"order": 2, "time_label": "30 min", "title": "Egyptian Gallery", "description": "Rosetta Stone and mummies"},
            {"order": 3, "time_label": "1 hr", "title": "Greek & Roman Galleries", "description": "Parthenon sculptures"},
            {"order": 4, "time_label": "1.5 hr", "title": "Assyrian & Enlightenment", "description": "Final highlights"},
        ],
    },
    {
        "category": "Thames River",
        "name": "Thames Evening Dinner Cruise with Live Jazz",
        "slug": "thames-evening-dinner-cruise-live-jazz",
        "description_short": "Glide along the Thames at sunset enjoying a 4-course dinner, live jazz music, and stunning views of illuminated London.",
        "description_long": "Experience London's most romantic evening on this premium Thames dinner cruise. Sail past the Houses of Parliament, Tower Bridge, the Shard, and Canary Wharf as they sparkle under the night sky. Savor a freshly prepared 4-course British menu paired with a welcome glass of champagne. Live jazz musicians create the perfect atmosphere as you dine at elegantly set tables beside panoramic windows.",
        "activity_type": "dinner_cruise",
        "price_adult": 380.00,
        "price_child": 245.00,
        "duration_minutes": 180,
        "address": "Embankment Pier, Victoria Embankment, London WC2N 6NU",
        "lat": 51.5074, "lng": -0.1224,
        "highlights": ["4-course dinner with champagne", "Live jazz entertainment", "Panoramic views of illuminated London", "Pass Tower Bridge & Parliament", "3-hour evening cruise"],
        "included": ["4-course dinner", "Welcome champagne", "Live jazz music", "Window table seating"],
        "excluded": ["Additional drinks", "Hotel transfer", "Gratuities"],
        "source_urls": ["https://www.getyourguide.com/london-l57/thames-dinner-cruise", "https://www.viator.com/tours/London/Thames-Dinner-Cruise", "https://www.citycruises.com/london/dinner-cruises"],
        "search_query": "thames river dinner cruise london evening",
        "operator_name": "City Cruises London",
        "timeline": [
            {"order": 1, "time_label": "7:00 PM", "title": "Board at Embankment Pier", "description": "Welcome champagne on arrival"},
            {"order": 2, "time_label": "7:30 PM", "title": "Set Sail & Starter", "description": "Cruise towards Westminster"},
            {"order": 3, "time_label": "8:30 PM", "title": "Main Course & Live Jazz", "description": "Pass Tower Bridge"},
            {"order": 4, "time_label": "9:30 PM", "title": "Dessert & Return", "description": "Return to Embankment Pier"},
        ],
    },
    {
        "category": "Day Trips",
        "name": "Stonehenge, Bath & Cotswolds Full-Day Tour from London",
        "slug": "stonehenge-bath-cotswolds-full-day-tour",
        "description_short": "Visit three of England's most iconic destinations in one day — mysterious Stonehenge, elegant Bath, and the idyllic Cotswolds.",
        "description_long": "Escape London for a day and discover England's countryside treasures. Begin with the prehistoric wonder of Stonehenge, where you'll explore the ancient stone circle and world-class visitor centre. Continue to the honey-coloured villages of the Cotswolds for a lunch stop in Lacock or Castle Combe. End the day in the Georgian city of Bath, visiting the Roman Baths and admiring the Royal Crescent and Pulteney Bridge. Travel in a luxury air-conditioned coach with expert commentary.",
        "activity_type": "day_trip",
        "price_adult": 340.00,
        "price_child": 210.00,
        "duration_minutes": 720,
        "address": "Victoria Coach Station, 164 Buckingham Palace Rd, London SW1W 9TP",
        "lat": 51.4920, "lng": -0.1482,
        "highlights": ["Stonehenge inner circle access", "Charming Cotswolds villages", "Roman Baths in Bath", "Luxury coach with WiFi", "Expert guide commentary"],
        "included": ["Luxury coach transport", "Expert guide", "Stonehenge entry ticket", "Roman Baths entry ticket"],
        "excluded": ["Lunch", "Hotel pickup (available as upgrade)", "Gratuities"],
        "source_urls": ["https://www.getyourguide.com/london-l57/stonehenge-bath-day-trip", "https://www.viator.com/tours/London/Stonehenge-Bath-Cotswolds"],
        "search_query": "stonehenge bath cotswolds english countryside tour",
        "operator_name": "Premium Tours London",
        "timeline": [
            {"order": 1, "time_label": "8:00 AM", "title": "Depart Victoria", "description": "Board luxury coach"},
            {"order": 2, "time_label": "10:00 AM", "title": "Stonehenge", "description": "2 hours at the ancient stone circle"},
            {"order": 3, "time_label": "1:00 PM", "title": "Cotswolds Village", "description": "Lunch stop in Lacock"},
            {"order": 4, "time_label": "3:00 PM", "title": "Bath", "description": "Roman Baths and free time"},
            {"order": 5, "time_label": "6:00 PM", "title": "Return to London", "description": "Arrive ~8 PM"},
        ],
    },
    {
        "category": "Harry Potter & Film",
        "name": "Warner Bros Studio Tour – The Making of Harry Potter",
        "slug": "warner-bros-studio-tour-making-harry-potter",
        "description_short": "Walk through the actual sets, costumes, and props used in the Harry Potter films at Warner Bros Studios.",
        "description_long": "Step behind the scenes of the world's most beloved film series at Warner Bros Studio Tour London. Walk through the Great Hall, explore Diagon Alley, and board the Hogwarts Express on Platform 9¾. See original costumes, props, and special effects secrets spanning all eight films. Try butterbeer in the backlot cafe and marvel at the incredible 1:24 scale model of Hogwarts Castle. Includes return luxury coach transfer from central London.",
        "activity_type": "studio_tour",
        "price_adult": 350.00,
        "price_child": 280.00,
        "duration_minutes": 420,
        "address": "Warner Bros Studios, Studio Tour Dr, Leavesden WD25 7LR",
        "lat": 51.6904, "lng": -0.4182,
        "highlights": ["Walk through the Great Hall", "Visit Diagon Alley", "Board Hogwarts Express", "Try butterbeer", "See Hogwarts Castle model"],
        "included": ["Studio entry ticket", "Return coach transfer from London", "Digital guide"],
        "excluded": ["Food & drinks (available for purchase)", "Souvenirs", "Private guide"],
        "source_urls": ["https://www.getyourguide.com/london-l57/harry-potter-studio-tour", "https://www.viator.com/tours/London/Harry-Potter-Warner-Bros-Studio"],
        "search_query": "harry potter warner bros studio tour hogwarts",
        "operator_name": "Warner Bros Studio Tour London",
        "timeline": [
            {"order": 1, "time_label": "9:00 AM", "title": "Coach Departs London", "description": "Depart from Baker Street"},
            {"order": 2, "time_label": "10:30 AM", "title": "Arrive at Studios", "description": "Enter the Great Hall"},
            {"order": 3, "time_label": "12:00 PM", "title": "Backlot & Butterbeer", "description": "Outdoor sets and Platform 9¾"},
            {"order": 4, "time_label": "2:00 PM", "title": "Hogwarts Castle Model", "description": "Grand finale"},
            {"order": 5, "time_label": "3:00 PM", "title": "Return to London", "description": "Arrive ~4:30 PM"},
        ],
    },
    {
        "category": "Food & Drink",
        "name": "London East End Food Tour with 10 Tastings",
        "slug": "london-east-end-food-tour-10-tastings",
        "description_short": "Eat your way through London's multicultural East End with 10 generous tastings from Brick Lane to Spitalfields.",
        "description_long": "Discover London's vibrant food scene on this guided walking tour through the East End. Sample 10 delicious tastings including freshly baked beigels from the legendary Beigel Bake, authentic Bangladeshi curry on Brick Lane, artisan cheeses at Spitalfields Market, traditional fish and chips, and craft chocolate. Your foodie guide shares fascinating stories about the area's immigrant history and how each community shaped London's culinary landscape.",
        "activity_type": "food_tour",
        "price_adult": 220.00,
        "price_child": 160.00,
        "duration_minutes": 210,
        "address": "Liverpool Street Station, London EC2M 7QH",
        "lat": 51.5178, "lng": -0.0823,
        "highlights": ["10 generous food tastings", "Brick Lane curry tasting", "Famous Beigel Bake stop", "Spitalfields Market visit", "Cultural & food history"],
        "included": ["10 food tastings", "Expert food guide", "Water bottle", "Food map of East End"],
        "excluded": ["Additional drinks", "Hotel transfer", "Gratuities"],
        "source_urls": ["https://www.getyourguide.com/london-l57/east-end-food-tour", "https://www.viator.com/tours/London/East-End-Food-Tour"],
        "search_query": "london east end brick lane food market tasting",
        "operator_name": "Eating London Tours",
        "timeline": [
            {"order": 1, "time_label": "Start", "title": "Meet at Liverpool Street", "description": "Introduction to East End food culture"},
            {"order": 2, "time_label": "30 min", "title": "Spitalfields Market", "description": "Artisan cheese and charcuterie"},
            {"order": 3, "time_label": "1 hr", "title": "Brick Lane", "description": "Curry and beigels"},
            {"order": 4, "time_label": "2.5 hr", "title": "Final Stop", "description": "Fish & chips and craft chocolate"},
        ],
    },
    {
        "category": "Shows & Entertainment",
        "name": "The Phantom of the Opera – West End Theatre Tickets",
        "slug": "phantom-of-the-opera-west-end-theatre-tickets",
        "description_short": "See the longest-running West End musical at His Majesty's Theatre — a spectacular experience of music, drama, and stagecraft.",
        "description_long": "Witness the magic of Andrew Lloyd Webber's masterpiece at its original London home. The Phantom of the Opera has been thrilling West End audiences since 1986 with its unforgettable score, stunning chandelier drop, and the haunting underground lake. Premium stalls seating gives you the best views of the spectacular sets and costumes. The perfect London theatre experience for first-time visitors and returning fans alike.",
        "activity_type": "theatre_show",
        "price_adult": 330.00,
        "price_child": 250.00,
        "duration_minutes": 150,
        "address": "His Majesty's Theatre, Haymarket, London SW1Y 4QR",
        "lat": 51.5093, "lng": -0.1316,
        "highlights": ["Iconic West End musical", "Premium stalls seating", "Spectacular chandelier scene", "His Majesty's Theatre", "2.5 hour performance"],
        "included": ["Premium stalls ticket", "Programme booklet", "Cloakroom service"],
        "excluded": ["Interval drinks", "Hotel transfer", "Dinner"],
        "source_urls": ["https://www.londontheatredirect.com/phantom-of-the-opera", "https://www.getyourguide.com/london-l57/phantom-of-the-opera-tickets"],
        "search_query": "london west end theatre musical show performance",
        "operator_name": "London Theatre Direct",
        "timeline": [
            {"order": 1, "time_label": "7:00 PM", "title": "Arrive at Theatre", "description": "Collect tickets at box office"},
            {"order": 2, "time_label": "7:30 PM", "title": "Act One", "description": "The phantom is introduced"},
            {"order": 3, "time_label": "8:30 PM", "title": "Interval", "description": "20-minute break"},
            {"order": 4, "time_label": "9:00 PM", "title": "Act Two", "description": "The dramatic finale"},
        ],
    },
    {
        "category": "Passes & Combos",
        "name": "London Explorer Pass – Choose 3 to 7 Attractions",
        "slug": "london-explorer-pass-choose-3-7-attractions",
        "description_short": "Save up to 50% on London's top attractions with a flexible pass — choose from 80+ experiences at your own pace.",
        "description_long": "Get the most out of London with the Explorer Pass. Choose from 80+ top attractions and experiences including the Tower of London, Westminster Abbey, Thames River Cruise, London Zoo, Madame Tussauds, the Shard, and many more. Your digital pass activates on first use and is valid for 60 days, giving you ultimate flexibility. Simply show your pass on your phone at each attraction for instant entry. Save up to 50% compared to buying individual tickets.",
        "activity_type": "attraction_pass",
        "price_adult": 275.00,
        "price_child": 180.00,
        "duration_minutes": 4320,
        "address": "Various locations across London",
        "lat": 51.5074, "lng": -0.1278,
        "highlights": ["Choose from 80+ attractions", "Save up to 50%", "Valid for 60 days", "Digital pass on phone", "Includes top landmarks"],
        "included": ["Digital Explorer Pass", "Access to chosen attractions", "Mobile app guide", "City map"],
        "excluded": ["Transport", "Food & drinks", "Hotel accommodation"],
        "source_urls": ["https://www.getyourguide.com/london-l57/explorer-pass", "https://www.viator.com/tours/London/London-Explorer-Pass"],
        "search_query": "london city pass sightseeing attractions combo",
        "operator_name": "Go City",
        "timeline": [
            {"order": 1, "time_label": "Day 1", "title": "Activate Your Pass", "description": "Visit your first attraction"},
            {"order": 2, "time_label": "Day 1-2", "title": "Top Landmarks", "description": "Tower of London, Westminster Abbey"},
            {"order": 3, "time_label": "Day 2-3", "title": "Experiences", "description": "Thames cruise, Madame Tussauds"},
        ],
    },
    {
        "category": "Transfers",
        "name": "London Heathrow Airport Private Transfer",
        "slug": "london-heathrow-airport-private-transfer",
        "description_short": "Stress-free private transfer between Heathrow Airport and central London in a luxury Mercedes vehicle.",
        "description_long": "Start or end your London trip in comfort with a premium private airport transfer. Your professional chauffeur meets you in the arrivals hall with a name board, assists with luggage, and drives you directly to your hotel or destination in a luxury Mercedes E-Class or V-Class. Complimentary waiting time of 60 minutes for flight delays. Available 24/7 with real-time flight tracking and free cancellation up to 24 hours before.",
        "activity_type": "private_transfer",
        "price_adult": 295.00,
        "price_child": 0.00,
        "duration_minutes": 75,
        "address": "London Heathrow Airport, Longford TW6",
        "lat": 51.4700, "lng": -0.4543,
        "highlights": ["Professional chauffeur", "Meet & greet at arrivals", "Mercedes luxury vehicle", "60-min free waiting time", "Flight tracking included"],
        "included": ["Private luxury vehicle", "Professional chauffeur", "Meet & greet service", "Luggage assistance", "Flight monitoring"],
        "excluded": ["Return transfer", "Toll charges", "Additional stops"],
        "source_urls": ["https://www.getyourguide.com/london-l57/heathrow-private-transfer", "https://www.viator.com/tours/London/Heathrow-Airport-Transfer"],
        "search_query": "london heathrow airport luxury car transfer chauffeur",
        "operator_name": "London Airport Transfers",
        "timeline": [
            {"order": 1, "time_label": "Arrival", "title": "Meet at Arrivals", "description": "Driver with name board"},
            {"order": 2, "time_label": "10 min", "title": "Luggage & Vehicle", "description": "Mercedes E-Class or V-Class"},
            {"order": 3, "time_label": "45-75 min", "title": "Drive to Hotel", "description": "Direct route to central London"},
        ],
    },
    {
        "category": "Sports & Outdoor",
        "name": "Wembley Stadium Guided Behind-the-Scenes Tour",
        "slug": "wembley-stadium-guided-behind-scenes-tour",
        "description_short": "Go behind the scenes at Wembley Stadium — visit the royal box, players' tunnel, changing rooms, and press conference area.",
        "description_long": "Experience the home of English football like never before. This exclusive guided tour takes you through the players' tunnel where legends have walked, into the England changing room, up to the Royal Box with its unrivalled view of the pitch, and into the press conference room where managers face the media. Your passionate guide shares stories of World Cup finals, FA Cup dramas, and legendary concerts. Photo opportunities at every turn.",
        "activity_type": "stadium_tour",
        "price_adult": 125.00,
        "price_child": 75.00,
        "duration_minutes": 90,
        "address": "Wembley Stadium, London HA9 0WS",
        "lat": 51.5560, "lng": -0.2796,
        "highlights": ["Players' tunnel walk", "England changing room", "Royal Box access", "Press conference room", "Pitch-side views"],
        "included": ["Guided stadium tour", "Access to all behind-the-scenes areas", "Photo opportunities"],
        "excluded": ["Food & drinks", "Matchday access", "Hotel transfer"],
        "source_urls": ["https://www.getyourguide.com/london-l57/wembley-stadium-tour", "https://www.wembleystadium.com/tours"],
        "search_query": "wembley stadium football tour london sports",
        "operator_name": "Wembley Stadium Tours",
        "timeline": [
            {"order": 1, "time_label": "Start", "title": "Welcome & Introduction", "description": "Meet at Bobby Moore statue"},
            {"order": 2, "time_label": "20 min", "title": "Changing Rooms", "description": "England team dressing room"},
            {"order": 3, "time_label": "45 min", "title": "Players' Tunnel", "description": "Walk out to the pitch"},
            {"order": 4, "time_label": "1 hr", "title": "Royal Box", "description": "Panoramic stadium views"},
        ],
    },
    {
        "category": "Night Tours",
        "name": "Jack the Ripper Interactive Walking Tour",
        "slug": "jack-the-ripper-interactive-walking-tour",
        "description_short": "Walk the dark streets of Whitechapel on this chilling interactive tour uncovering the mystery of Jack the Ripper.",
        "description_long": "Descend into the shadowy streets of Victorian Whitechapel and investigate history's most infamous unsolved murders. Your expert Ripperologist guide leads you through the actual murder sites, using original police photographs, maps, and witness statements projected on walls via handheld devices. Examine the evidence, debate the suspects, and form your own theory. This atmospheric evening tour takes you through dimly lit alleyways and historic pubs where the story unfolded in 1888.",
        "activity_type": "walking_tour",
        "price_adult": 85.00,
        "price_child": 60.00,
        "duration_minutes": 120,
        "address": "Aldgate East Station, London E1 7PT",
        "lat": 51.5154, "lng": -0.0726,
        "highlights": ["Expert Ripperologist guide", "Original crime scene locations", "Interactive evidence examination", "Atmospheric night walk", "Historic Whitechapel pubs"],
        "included": ["Expert guide", "Interactive handheld device", "Evidence pack", "Walking route map"],
        "excluded": ["Drinks at pub stops", "Hotel transfer", "Dinner"],
        "source_urls": ["https://www.getyourguide.com/london-l57/jack-the-ripper-tour", "https://www.viator.com/tours/London/Jack-the-Ripper-Walking-Tour"],
        "search_query": "jack the ripper whitechapel london night ghost tour",
        "operator_name": "London Walks",
        "timeline": [
            {"order": 1, "time_label": "7:30 PM", "title": "Meet at Aldgate East", "description": "Introduction to 1888 Whitechapel"},
            {"order": 2, "time_label": "8:00 PM", "title": "First Murder Site", "description": "Mary Ann Nichols case"},
            {"order": 3, "time_label": "8:30 PM", "title": "Evidence Analysis", "description": "Interactive suspect profiles"},
            {"order": 4, "time_label": "9:15 PM", "title": "Final Verdict", "description": "Who was Jack the Ripper?"},
        ],
    },
    {
        "category": "Family & Kids",
        "name": "London Zoo Family Experience with Feeding Sessions",
        "slug": "london-zoo-family-experience-feeding-sessions",
        "description_short": "A fun-filled family day at ZSL London Zoo with keeper talks, animal feeding sessions, and interactive exhibits.",
        "description_long": "Create unforgettable family memories at London Zoo, home to over 750 species in the heart of Regent's Park. Watch penguins being fed, meet the meerkats, and walk through the tropical Rainforest Life exhibit. Children will love the interactive B.U.G.S exhibit, the splash park in summer, and the chance to come face-to-face with gorillas at Gorilla Kingdom. Your family ticket includes keeper talks throughout the day and access to all exhibits.",
        "activity_type": "zoo_experience",
        "price_adult": 155.00,
        "price_child": 105.00,
        "duration_minutes": 300,
        "address": "ZSL London Zoo, Outer Cir, London NW1 4RY",
        "lat": 51.5353, "lng": -0.1534,
        "highlights": ["750+ animal species", "Keeper talks & feeding sessions", "Gorilla Kingdom", "Rainforest Life walk-through", "Children's splash park"],
        "included": ["Full day entry", "All exhibits access", "Keeper talk schedule", "Zoo map & guide"],
        "excluded": ["Food & drinks", "Souvenir photos", "Hotel transfer"],
        "source_urls": ["https://www.getyourguide.com/london-l57/london-zoo-tickets", "https://www.zsl.org/zsl-london-zoo"],
        "search_query": "london zoo animals family kids penguin gorilla",
        "operator_name": "ZSL London Zoo",
        "timeline": [
            {"order": 1, "time_label": "10:00 AM", "title": "Arrive & Land of the Lions", "description": "See the Asiatic lions"},
            {"order": 2, "time_label": "11:00 AM", "title": "Penguin Beach Feeding", "description": "Watch the keeper talk"},
            {"order": 3, "time_label": "12:30 PM", "title": "Gorilla Kingdom", "description": "Meet the western lowland gorillas"},
            {"order": 4, "time_label": "2:00 PM", "title": "Rainforest Life", "description": "Walk-through tropical experience"},
        ],
    },
    {
        "category": "Luxury & Private",
        "name": "Private London Helicopter Flight over Central London",
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
        "timeline": [
            {"order": 1, "time_label": "Arrival", "title": "Check-in at Heliport", "description": "Safety briefing and champagne"},
            {"order": 2, "time_label": "10 min", "title": "Take Off", "description": "Lift off over the Thames"},
            {"order": 3, "time_label": "20 min", "title": "Central London Circuit", "description": "All major landmarks"},
            {"order": 4, "time_label": "30 min", "title": "Landing & Photos", "description": "Return to Battersea Heliport"},
        ],
    },
    {
        "category": "Seasonal & Events",
        "name": "London Christmas Lights Walking Tour with Mulled Wine",
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
        "timeline": [
            {"order": 1, "time_label": "5:00 PM", "title": "Meet at Oxford Circus", "description": "Start at the Oxford Street lights"},
            {"order": 2, "time_label": "5:30 PM", "title": "Carnaby Street", "description": "Famous themed decorations"},
            {"order": 3, "time_label": "6:15 PM", "title": "Regent Street & Mulled Wine", "description": "First warm-up stop"},
            {"order": 4, "time_label": "7:00 PM", "title": "Covent Garden", "description": "Christmas tree and final mulled wine"},
        ],
    },
]


def _dedup_hash(name: str, city: str, category: str) -> str:
    raw = f"{name.lower().strip()}|{city.lower().strip()}|{category.lower().strip()}"
    return hashlib.md5(raw.encode()).hexdigest()


async def seed():
    from app.db.base import async_session_factory
    from app.db.models.activities import Activity, ActivityTimeline
    from app.db.models.reviews import ProductReview
    from app.services.image_service import fetch_and_upload_images

    city_id = uuid.UUID(LONDON_CITY_ID)

    for i, cat in enumerate(CATEGORIES):
        logger.info("━" * 60)
        logger.info("[%d/15] Processing: %s — %s", i + 1, cat["category"], cat["name"])

        product_id = str(uuid.uuid4())

        # ── Fetch real images from Freepik → Cloudinary ──────────────
        logger.info("  Searching Freepik for '%s'...", cat["search_query"])
        try:
            gallery = await fetch_and_upload_images(
                product_name=cat["search_query"],
                city="London",
                product_id=product_id,
                product_type="activities",
                num_images=8,
            )
            logger.info("  Got %d images uploaded to Cloudinary", len(gallery))
        except Exception as exc:
            logger.error("  Image fetch failed: %s", exc)
            gallery = []

        cover_url = gallery[0]["url"] if gallery else None

        # ── Create Activity record ───────────────────────────────────
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
                meta_title=f"{cat['name']} | Book Online | Rayna Tours",
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

            # Add timeline items
            for t in cat.get("timeline", []):
                tl = ActivityTimeline(
                    activity_id=uuid.UUID(product_id),
                    order=t["order"],
                    time_label=t.get("time_label"),
                    title=t["title"],
                    description=t.get("description"),
                )
                db.add(tl)

            # Add sample reviews
            sample_reviews = [
                {"name": "Sarah Mitchell", "rating": 5.0, "title": "Amazing experience!", "text": f"The {cat['name']} was absolutely incredible. Everything was well-organized and our guide was very knowledgeable. Would definitely recommend to anyone visiting London.", "platform": "tripadvisor"},
                {"name": "James Thompson", "rating": 5.0, "title": "Highly recommended", "text": f"One of the best things we did in London. The {cat['category'].lower()} experience exceeded our expectations. Great value for money.", "platform": "google"},
                {"name": "Emma Lewis", "rating": 4.0, "title": "Very enjoyable", "text": f"Had a wonderful time. The only minor issue was the waiting time at the start, but once it got going, it was brilliant. The {cat['category'].lower()} was top-notch.", "platform": "tripadvisor"},
                {"name": "David Chen", "rating": 5.0, "title": "Must-do in London!", "text": f"If you're visiting London, this is a must. The {cat['name']} gives you a genuine London experience. Our group had a fantastic time.", "platform": "google"},
                {"name": "Olivia Martinez", "rating": 4.0, "title": "Great day out", "text": f"Really enjoyed the {cat['category'].lower()} experience. Well worth the price. Just make sure to book in advance as it fills up quickly.", "platform": "tripadvisor"},
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
            logger.info("  ✓ Saved activity + %d timeline items + 5 reviews", len(cat.get("timeline", [])))

        # Small delay between categories to avoid rate limits
        if i < len(CATEGORIES) - 1:
            await asyncio.sleep(2)

    logger.info("━" * 60)
    logger.info("DONE! 15 London activities seeded with real Freepik → Cloudinary images.")
    logger.info("Check http://localhost:3000/activities to see results!")


if __name__ == "__main__":
    asyncio.run(seed())
