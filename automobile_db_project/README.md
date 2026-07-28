# Automobile Company Database — CSE 241/341 Project

Stack: **Python (Flask) + MySQL + CSS**

## What's here

| File | Purpose |
|---|---|
| `schema.sql` | Full relational schema — brands, platforms, models, vehicles, dealers, customers, suppliers, parts, plants, sales, locator inquiries |
| `db.py` | Connection helper (`get_connection`, `dict_cursor`) + `init_db()` to (re)build the schema against MySQL |
| `generate_data.py` | Test data generator — reference data plus vehicles/customers/sales, biased so every required query has a non-trivial answer |
| `queries.py` | All six required client queries from the handout |
| `app.py` | Flask app implementing the locator, customer search, and marketing/OLAP interfaces |
| `dba_cli.py` | Minimal SQL REPL for the DBA interface |
| `templates/`, `static/style.css` | Jinja2 HTML templates + shared stylesheet |

The E-R diagram and relational-design writeup live alongside this
code (see the accompanying database notes) and are maintained
separately from this repo since the ER model and the final mock
dataset are being finalized by a project partner in parallel with
this implementation.

## Setup

1. **Install MySQL** if you don't have it.

   <details>
   <summary><b>macOS</b> (Homebrew)</summary>

   ```bash
   brew install mysql
   brew services start mysql
   mysql_secure_installation   # optional: set a root password, etc.
   ```
   </details>

   <details>
   <summary><b>Windows</b></summary>

   Download and run the installer from
   [dev.mysql.com/downloads/installer](https://dev.mysql.com/downloads/installer/)
   (choose "MySQL Server"). The installer walks you through setting
   a root password and starts the MySQL service automatically. Then
   use **MySQL Command Line Client** (installed alongside it) or
   PowerShell/cmd for the commands below.
   </details>

   <details>
   <summary><b>Linux</b> (Debian/Ubuntu)</summary>

   ```bash
   sudo apt update
   sudo apt install mysql-server
   sudo systemctl start mysql
   sudo mysql_secure_installation   # optional
   ```
   </details>

   <details>
   <summary>Alternative: Docker (any OS)</summary>

   ```bash
   docker run --name automobile-mysql -e MYSQL_ROOT_PASSWORD=yourpassword -p 3306:3306 -d mysql:8
   ```
   No local MySQL install needed — the container exposes MySQL on
   `localhost:3306` just like a native install.
   </details>

   Verify it's running and check the version:
   ```bash
   mysql --version
   ```

2. **Create the database:**
   ```sql
   mysql -u root -p
   CREATE DATABASE automobile_db;
   exit
   ```

3. **Set up Python and install Flask:**
   ```bash
   python -m venv venv
   source venv/bin/activate      # or venv\Scripts\activate on Windows
   pip install -r requirements.txt
   ```
   `requirements.txt` pins the exact versions used
   (`Flask==3.0.3`, `mysql-connector-python==9.0.0`), so this one
   command installs both Flask and the MySQL driver together.
   If you'd rather install Flask by itself first to confirm the
   toolchain works:
   ```bash
   pip install Flask
   flask --version
   ```

4. **Point the code at your MySQL login** by setting environment
   variables (a template is provided in `.env.example` — copy it to
   `.env` and fill in your own values, or export them directly):
   ```bash
   export DB_HOST=localhost
   export DB_USER=root
   export DB_PASSWORD=yourpassword
   export DB_NAME=automobile_db
   ```
   No credentials are hardcoded anywhere in the code, so this repo
   is safe to publish publicly (e.g. on GitHub) as-is.

5. **Build and populate:**
   ```bash
   python db.py                  # builds tables from schema.sql
   python generate_data.py       # rebuilds schema + populates test data
   python app.py                 # starts the web app at http://127.0.0.1:5000
   ```
   (`generate_data.py` calls `init_db()` itself, so running it alone
   is enough for a fresh build + populate in one step.)

DBA interface: `python dba_cli.py` in a separate terminal.

## Interfaces (handout requirement 5)

| Interface | How to reach it |
|---|---|
| Database administrator | `python dba_cli.py` — raw SQL REPL |
| Vehicle locator service | `http://127.0.0.1:5000/locator` |
| Customer web search | `http://127.0.0.1:5000/search` |
| Marketing / OLAP reports | `http://127.0.0.1:5000/marketing` |

## Design decisions made along the way

These are the judgment calls the handout deliberately leaves open
("the manager... is not computer literate so the specifications
should not be viewed as necessarily... complete"), documented here
so a reader doesn't have to reverse-engineer the reasoning from the
code alone:

- **Badge engineering / ISA relationship** — resolved with a
  `platforms` table. Two `models` rows sharing a `platform_id` are
  declared badge-engineered siblings (mirrors the handout's own VW
  Routan / Chrysler minivan and Buick LaCrosse / Allure examples).
  See the comment block above `CREATE TABLE platforms` in
  `schema.sql`.
- **Body style** lives directly on `models` rather than as a
  separate weak entity, since no variant needs independent
  attributes beyond what's already tracked.
- **Asking price vs. sale price** — `vehicles.asking_price` is the
  pre-sale listed price shown in `/search` and `/locator`;
  `sales.sale_price` is the (possibly different, negotiated) price
  recorded once a sale actually happens.
- **Locator inquiry logging** — every `/locator` search is written
  to `locator_inquiries`, satisfying the handout's note that
  marketing wants to review these for product planning.
- **Inventory hold time** (query 6) is computed only over vehicles
  that have sold, not still-unsold current inventory. See the
  docstring on `longest_avg_inventory_time()` in `queries.py` for
  the reasoning and the alternative that was considered.
- **Query 5's month bucketing** aggregates convertible sales by
  calendar month across all years (`MONTH(sale_date)`), not by
  year+month, so it answers a seasonality question rather than
  duplicating query 3's year-over-year trend.

## Concurrency (handout requirement 6)

`db.py`'s `get_connection()` sets `autocommit = False`, so any place
the code performs multiple related writes — for example, recording
a sale and updating `vehicles.current_dealer_id` — can be wrapped as
a single transaction:

```python
conn = get_connection()
try:
    cur = conn.cursor()
    cur.execute("INSERT INTO sales (...) VALUES (...)", (...))
    cur.execute("UPDATE vehicles SET current_dealer_id = NULL WHERE vin = %s", (vin,))
    conn.commit()   # both succeed together
except Exception:
    conn.rollback() # or neither does
    raise
```

MySQL's InnoDB engine (used for every table in `schema.sql`)
enforces this at the storage-engine level, so the guarantee is real,
not just cosmetic.

## What's intentionally NOT in this repo

Per handout requirement 3, this submission does not include a dump
of the generated test data — `generate_data.py` is the program that
produces it, and the grading DBA has direct database access if a
specific row needs checking. Running `python generate_data.py`
reproduces a full dataset locally from a fixed random seed.

## A note on the sample dataset in `generate_data.py`

The brand/model/dealer/supplier lists currently in
`generate_data.py` are a **working placeholder** — real enough to
exercise every required query end to end (a defect window with
real hits, a seasonal convertible bump, one deliberately slow
dealer, a genuine income/gender spread), but not necessarily the
final dataset that ships with the graded submission. If the ER
diagram or the final mock dataset changes the entity shapes, only
the lookup lists at the top of `generate_data.py` need to change —
the generation logic underneath (date spread, seasonal bias, the
recall window) carries over unchanged.
