"""
generate_data.py — populates the database with test data.

Produces enough of a working dataset to exercise all six required
queries end to end: badge engineering, multi-brand dealers, a
defect window, income/gender spread, a seasonal convertible bump,
and one deliberately slow dealer. The randomness below is biased on
purpose (rather than left uniform) so each query has a real,
non-trivial answer instead of a coincidental tie or an empty result.
"""

import random
from datetime import date, timedelta
from db import get_connection, init_db, DatabaseConnectionError

random.seed(42)  # fixed seed = reproducible test data while debugging


# brand_name -> [(model_name, body_style, platform_name_or_None), ...]
# Two models sharing a platform_name are badge-engineered siblings
# (same underlying vehicle, different brand) — see schema.sql's
# platforms table.
BRANDS_AND_MODELS = {
    "Chevrolet": [
        ("Malibu", "4-door", None),
        ("Equinox", "SUV", None),
        ("Camaro", "coupe", None),
    ],
    "Buick": [
        ("Enclave", "SUV", None),
        ("LaCrosse", "4-door", None),
        ("Lucerne", "4-door", None),
        ("Encore", "SUV", "GM_Gamma"),
    ],
    "GMC": [
        ("Terrain", "SUV", "GM_Gamma"),
        ("Acadia", "SUV", None),
    ],
    "Cadillac": [
        ("CTS", "4-door", None),
        ("Escalade", "SUV", None),
    ],
    "Volkswagen": [
        ("Jetta", "4-door", None),
        ("Beetle", "convertible", None),
        ("Routan", "wagon", "VW_Chrysler_RT"),
    ],
    "Chrysler": [
        ("300", "4-door", None),
        ("Town and Country", "wagon", "VW_Chrysler_RT"),
        ("Sebring", "convertible", None),
    ],
}

DEALER_NAMES = [
    "Riverside Auto Group", "Lakeside Motors", "Summit City Dealers",
    "Northgate Automotive", "Crestview Motor Sales", "Harbor Point Auto",
]

SUPPLIER_NAMES = ["Getrag", "Bosch", "Delphi", "ZF Friedrichshafen"]

PARTS_BY_SUPPLIER = {
    "Getrag": ["Transmission"],
    "Bosch": ["Fuel Injector", "Braking System"],
    "Delphi": ["Wiring Harness"],
    "ZF Friedrichshafen": ["Transmission", "Steering System"],
}

PLANT_NAMES = [
    ("Lansing Assembly", "assembly"),
    ("Toledo Parts Complex", "parts"),
    ("Arlington Assembly", "assembly"),
]

COLORS = ["Black", "White", "Silver", "Blue", "Red", "Gray"]
ENGINES = ["2.0L I4", "3.6L V6", "5.3L V8"]
TRANSMISSIONS = ["6-Speed Automatic", "8-Speed Automatic", "Manual"]

BASE_PRICE_BY_BODY_STYLE = {
    "4-door": 27000, "SUV": 35000, "convertible": 41000,
    "coupe": 32000, "wagon": 30000,
}

# Fixed window so find_affected_vehicles() in queries.py has a
# real, non-empty answer to find, while vehicles outside this
# window/supplier still exist to prove the query isn't just
# returning everything.
DEFECT_WINDOW_START = date.today() - timedelta(days=500)
DEFECT_WINDOW_END = date.today() - timedelta(days=430)


def seed_reference_data(conn):
    """
    Insert platforms, brands, models, dealers (+ carried brands),
    suppliers (+ parts), and plants (+ assembled models). Returns a
    dict of lookup structures the later generators need, so nobody
    re-queries the database for IDs it just inserted.
    """
    cur = conn.cursor()

    # platforms first, so models can reference platform_id
    platform_names = {
        p for models in BRANDS_AND_MODELS.values()
        for (_, _, p) in models if p is not None
    }
    platform_ids = {}
    for name in platform_names:
        cur.execute("INSERT INTO platforms (platform_name) VALUES (%s)", (name,))
        platform_ids[name] = cur.lastrowid

    brand_ids = {}
    model_ids_by_brand = {}
    for brand_name, models in BRANDS_AND_MODELS.items():
        cur.execute("INSERT INTO brands (brand_name) VALUES (%s)", (brand_name,))
        brand_ids[brand_name] = cur.lastrowid
        model_ids_by_brand[brand_name] = []
        for model_name, body_style, platform_name in models:
            platform_id = platform_ids.get(platform_name)
            cur.execute(
                """INSERT INTO models (brand_id, model_name, body_style, platform_id)
                   VALUES (%s, %s, %s, %s)""",
                (brand_ids[brand_name], model_name, body_style, platform_id),
            )
            model_ids_by_brand[brand_name].append(cur.lastrowid)

    # dealers, each carrying a random subset of brands
    dealer_ids = []
    for name in DEALER_NAMES:
        cur.execute(
            "INSERT INTO dealers (dealer_name, address, phone) VALUES (%s, %s, %s)",
            (name, f"{random.randint(100, 9999)} Main St", f"555-{random.randint(1000, 9999)}"),
        )
        dealer_ids.append(cur.lastrowid)
        carried = random.sample(
            list(brand_ids.values()), k=random.randint(2, len(brand_ids))
        )
        for bid in carried:
            cur.execute(
                "INSERT INTO dealer_brands (dealer_id, brand_id) VALUES (%s, %s)",
                (dealer_ids[-1], bid),
            )

    # suppliers, and the parts each one makes
    supplier_ids = {}
    part_ids_by_supplier = {}
    for name in SUPPLIER_NAMES:
        cur.execute("INSERT INTO suppliers (supplier_name) VALUES (%s)", (name,))
        supplier_ids[name] = cur.lastrowid
        part_ids_by_supplier[name] = []

    # plants
    plant_id_by_type = {"assembly": [], "parts": []}
    for name, ptype in PLANT_NAMES:
        cur.execute(
            "INSERT INTO plants (plant_name, plant_type) VALUES (%s, %s)",
            (name, ptype),
        )
        plant_id_by_type[ptype].append(cur.lastrowid)

    # parts, each tied to a supplier and to one supplying plant
    for supplier_name, parts in PARTS_BY_SUPPLIER.items():
        for part_name in parts:
            supplying_plant = random.choice(plant_id_by_type["parts"])
            cur.execute(
                "INSERT INTO parts (part_name, supplier_id, supplying_plant_id) VALUES (%s, %s, %s)",
                (part_name, supplier_ids[supplier_name], supplying_plant),
            )
            part_ids_by_supplier[supplier_name].append(cur.lastrowid)

    # link every model to a Transmission part and an assembly
    # plant, so vehicle_parts generation has something to draw from
    transmission_part_ids = [
        pid for sup, parts in PARTS_BY_SUPPLIER.items()
        for pname, pid in zip(parts, part_ids_by_supplier[sup]) if pname == "Transmission"
    ]
    model_ids_all = [mid for ids in model_ids_by_brand.values() for mid in ids]
    for mid in model_ids_all:
        part_id = random.choice(transmission_part_ids)
        cur.execute("INSERT INTO model_parts (model_id, part_id) VALUES (%s, %s)", (mid, part_id))
        plant_id = random.choice(plant_id_by_type["assembly"])
        cur.execute("INSERT INTO plant_models (plant_id, model_id) VALUES (%s, %s)", (plant_id, mid))

    conn.commit()
    return {
        "brand_ids": brand_ids,
        "model_ids_by_brand": model_ids_by_brand,
        "dealer_ids": dealer_ids,
        "plant_id_by_type": plant_id_by_type,
        "supplier_ids": supplier_ids,
    }


def _random_date(start, end):
    delta_days = (end - start).days
    return start + timedelta(days=random.randint(0, delta_days))


def generate_vehicles(conn, ctx, count=500):
    """
    Pick a random model per vehicle, make up a VIN, pick
    color/engine/transmission, and spread manufacture_date over the
    last 3 years (biased toward spring for convertibles, for query
    5's seasonal signal). manufacturing_plant_id is kept consistent
    with plant_models for that model_id rather than picked at random.
    """
    cur = conn.cursor()
    model_ids_all = [
        mid for ids in ctx["model_ids_by_brand"].values() for mid in ids
    ]

    cur.execute("SELECT model_id, body_style FROM models")
    body_style_by_model = {row[0]: row[1] for row in cur.fetchall()}

    # cache which assembly plant(s) each model can come from
    cur.execute("SELECT model_id, plant_id FROM plant_models")
    plants_by_model = {}
    for model_id, plant_id in cur.fetchall():
        plants_by_model.setdefault(model_id, []).append(plant_id)

    start_range = date.today() - timedelta(days=3 * 365)
    end_range = date.today() - timedelta(days=30)

    vins = []
    for i in range(count):
        model_id = random.choice(model_ids_all)
        body_style = body_style_by_model[model_id]

        vin = f"1G{i:06d}" + "".join(random.choices("ABCDEFGHJKLMNP0123456789", k=6))
        color = random.choice(COLORS)
        engine = random.choice(ENGINES)
        transmission = random.choice(TRANSMISSIONS)
        asking_price = round(
            BASE_PRICE_BY_BODY_STYLE.get(body_style, 30000) * random.uniform(0.95, 1.1), 2
        )

        if body_style == "convertible":
            # bias manufacture dates toward spring (Mar-Jun) so
            # "best month for convertibles" has a real signal to find
            year = random.randint(start_range.year, end_range.year)
            month = random.choice([3, 4, 5, 6])
            manufacture_date = date(year, month, random.randint(1, 28))
        else:
            manufacture_date = _random_date(start_range, end_range)

        plant_id = random.choice(plants_by_model[model_id])

        cur.execute(
            """INSERT INTO vehicles
               (vin, model_id, color, engine, transmission, asking_price,
                manufacture_date, manufacturing_plant_id)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (vin, model_id, color, engine, transmission, asking_price,
             manufacture_date, plant_id),
        )
        vins.append((vin, model_id, body_style, manufacture_date))

    conn.commit()
    return vins


def generate_vehicle_parts(conn, vins, ctx):
    """
    For each vehicle, link it (via vehicle_parts) to the part its
    model is compatible with, with install_date usually a few days
    before manufacture_date. A slice of vehicles gets its
    install_date forced into the defect window with a Getrag
    transmission so find_affected_vehicles() has real matches to
    return; everything else keeps its natural install_date.
    """
    cur = conn.cursor()

    cur.execute(
        "SELECT part_id FROM parts WHERE supplier_id = %s AND part_name = %s",
        (ctx["supplier_ids"]["Getrag"], "Transmission"),
    )
    getrag_transmission_ids = {row[0] for row in cur.fetchall()}

    for idx, (vin, model_id, body_style, manufacture_date) in enumerate(vins):
        cur.execute("SELECT part_id FROM model_parts WHERE model_id = %s", (model_id,))
        for (part_id,) in cur.fetchall():
            if part_id in getrag_transmission_ids and idx % 6 == 0:
                # force ~1 in 6 Getrag-transmission vehicles into the
                # recall window so the defect query has real hits
                install_date = _random_date(DEFECT_WINDOW_START, DEFECT_WINDOW_END)
            else:
                install_date = manufacture_date - timedelta(days=random.randint(0, 3))

            cur.execute(
                "INSERT INTO vehicle_parts (vin, part_id, install_date) VALUES (%s, %s, %s)",
                (vin, part_id, install_date),
            )
    conn.commit()


def generate_customers(conn, count=300):
    """
    Insert `count` customers with made-up names/address/phone,
    gender, and annual_income. Genders are drawn evenly and incomes
    from weighted bands (not a flat random range), so the gender/
    income breakdown query has a real spread to show.
    """
    cur = conn.cursor()
    first_names = ["Alex", "Jordan", "Taylor", "Morgan", "Casey", "Riley",
                   "Sam", "Jamie", "Drew", "Cameron"]
    last_names = ["Reed", "Novak", "Whitfield", "Alvarez", "Kim", "Patel",
                  "Nguyen", "Osei", "Brennan", "Sato"]
    genders = ["M", "F", "Other", "Prefer not to say"]

    customer_ids = []
    for _ in range(count):
        name = f"{random.choice(first_names)} {random.choice(last_names)}"
        gender = random.choices(genders, weights=[0.46, 0.46, 0.04, 0.04])[0]
        income_band = random.choices(
            [(20000, 40000), (40000, 80000), (80000, 150000), (150000, 260000)],
            weights=[0.2, 0.4, 0.3, 0.1],
        )[0]
        income = round(random.uniform(*income_band), 2)

        cur.execute(
            """INSERT INTO customers (full_name, address, phone, gender, annual_income)
               VALUES (%s, %s, %s, %s, %s)""",
            (name, f"{random.randint(100, 9999)} Oak Ave",
             f"555-{random.randint(1000, 9999)}", gender, income),
        )
        customer_ids.append(cur.lastrowid)

    conn.commit()
    return customer_ids


def generate_inventory_and_sales(conn, ctx, vins, customer_ids):
    """
    For each vehicle: assign it to a dealer that carries its brand,
    decide when it arrived, and decide whether/when it sells. Not
    every vehicle sells — some stay as unsold inventory, which gives
    the "longest average inventory hold" query real variation.
    """
    cur = conn.cursor()

    cur.execute("""
        SELECT db.dealer_id, b.brand_name FROM dealer_brands db
        JOIN brands b ON db.brand_id = b.brand_id
    """)
    dealers_by_brand = {}
    for dealer_id, brand_name in cur.fetchall():
        dealers_by_brand.setdefault(brand_name, []).append(dealer_id)

    # one dealer, deliberately, is the slow one — gives the
    # "longest average hold time" query a clear, defensible winner
    slow_dealer = ctx["dealer_ids"][0]

    for vin, model_id, body_style, manufacture_date in vins:
        cur.execute(
            """SELECT br.brand_name FROM models m
               JOIN brands br ON m.brand_id = br.brand_id
               WHERE m.model_id = %s""",
            (model_id,),
        )
        brand_name = cur.fetchone()[0]
        eligible_dealers = dealers_by_brand.get(brand_name, ctx["dealer_ids"])
        dealer_id = random.choice(eligible_dealers)

        arrived = manufacture_date + timedelta(days=random.randint(3, 14))
        cur.execute(
            "UPDATE vehicles SET current_dealer_id = %s, arrived_at_dealer_date = %s WHERE vin = %s",
            (dealer_id, arrived, vin),
        )

        # ~80% of vehicles eventually sell; the rest stay as
        # current, still-unsold inventory
        if random.random() < 0.8:
            if dealer_id == slow_dealer:
                hold_days = random.randint(45, 120)
            elif body_style == "convertible":
                # convertibles skew toward a shorter hold; they were
                # also manufactured biased toward spring, reinforcing
                # the seasonal signal query 5 looks for
                hold_days = random.randint(5, 40)
            else:
                hold_days = random.randint(5, 60)

            sale_date = arrived + timedelta(days=hold_days)
            if sale_date > date.today():
                continue  # don't record a sale in the future

            # sale_price derived from body-style base price plus
            # noise, so "top brands by dollar amount" isn't one flat
            # number across every sale
            base_price = BASE_PRICE_BY_BODY_STYLE.get(body_style, 30000)
            sale_price = round(base_price * random.uniform(0.9, 1.15), 2)
            customer_id = random.choice(customer_ids)

            cur.execute(
                """INSERT INTO sales (vin, dealer_id, customer_id, sale_date, sale_price)
                   VALUES (%s, %s, %s, %s, %s)""",
                (vin, dealer_id, customer_id, sale_date, sale_price),
            )

    conn.commit()


def main():
    init_db()  # rebuild schema fresh
    conn = get_connection()
    ctx = seed_reference_data(conn)
    vins = generate_vehicles(conn, ctx, count=500)
    generate_vehicle_parts(conn, vins, ctx)
    customer_ids = generate_customers(conn, count=300)
    generate_inventory_and_sales(conn, ctx, vins, customer_ids)
    conn.close()
    print("Data generation complete.")


if __name__ == "__main__":
    import sys
    try:
        main()
    except DatabaseConnectionError as e:
        sys.exit(str(e))
