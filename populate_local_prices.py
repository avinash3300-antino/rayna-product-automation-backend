"""
Populate local currency prices for all activities.
Converts AED prices to local currency based on city/country.
"""

import psycopg2

DATABASE_URL = "postgresql://postgres:Avinash1234@localhost:5432/rayna_db"

# City/Country → local currency mapping
CITY_CURRENCY_MAP = {
    "London": "GBP",
    "Cairo": "EGP",
    "Dubai": "AED",
    "Abu Dhabi": "AED",
    "Paris": "EUR",
    "Rome": "EUR",
    "Barcelona": "EUR",
    "Istanbul": "TRY",
    "Bangkok": "THB",
    "Mumbai": "INR",
    "New York": "USD",
}

# AED to local currency rates (1 local = X AED)
AED_TO_LOCAL = {
    "GBP": 4.70,
    "EGP": 0.075,
    "EUR": 4.00,
    "USD": 3.67,
    "INR": 0.044,
    "TRY": 0.11,
    "THB": 0.10,
    "SAR": 0.98,
    "AED": 1.0,
}


def main():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    cur.execute("""
        SELECT id, name, city, country, price_adult, price_from, currency
        FROM activities
        WHERE local_currency IS NULL
        ORDER BY name
    """)
    rows = cur.fetchall()
    total = len(rows)
    print(f"Found {total} activities to update\n")

    updated = 0
    skipped = 0

    for i, (aid, name, city, country, price_adult, price_from, currency) in enumerate(rows, 1):
        # Determine local currency from city
        local_cur = CITY_CURRENCY_MAP.get(city)
        if not local_cur:
            # Fallback: try country
            if country == "United Kingdom":
                local_cur = "GBP"
            elif country in ("France", "Spain", "Italy", "Germany", "Netherlands"):
                local_cur = "EUR"
            elif country == "United States":
                local_cur = "USD"
            elif country == "India":
                local_cur = "INR"
            elif country == "Egypt":
                local_cur = "EGP"
            else:
                print(f"[{i}/{total}] {name[:50]} - SKIPPED (unknown currency for {city}, {country})")
                skipped += 1
                continue

        # If currency is already local, no conversion needed
        if currency == local_cur:
            price_local = float(price_adult) if price_adult else 0
        else:
            rate = AED_TO_LOCAL.get(local_cur, 1.0)
            price_local = round(float(price_adult) / rate, 2) if price_adult and rate else 0

        cur.execute(
            "UPDATE activities SET local_currency = %s, price_local = %s WHERE id = %s",
            (local_cur, price_local, aid),
        )
        conn.commit()
        updated += 1
        short_name = name[:50].encode("ascii", "replace").decode()
        print(f"[{i}/{total}] {short_name} -> {local_cur} {price_local}")

    cur.close()
    conn.close()
    print(f"\nDone! Updated: {updated}, Skipped: {skipped}")


if __name__ == "__main__":
    main()
