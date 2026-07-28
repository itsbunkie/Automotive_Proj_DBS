"""
db.py -- single place that knows how to talk to the database.

Every other file (queries.py, app.py, dba_cli.py, generate_data.py)
imports get_connection()/dict_cursor() from here instead of opening
its own connection, so a connection detail only ever has to change
in one place.
"""

import os
import sys
import mysql.connector
from dotenv import load_dotenv

# Load variables from a .env file in the project root (if present) into
# the process environment. This runs once, at import time, so every
# script that imports db.py (app.py, dba_cli.py, generate_data.py) gets
# the same credentials without each partner having to `export` them by
# hand in every new terminal window.
load_dotenv()

# Env vars first so anyone running this can point it at their own
# MySQL instance without editing code; local defaults as a fallback.
DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "localhost"),
    "user": os.environ.get("DB_USER", "root"),
    "password": os.environ.get("DB_PASSWORD", ""),
    "database": os.environ.get("DB_NAME", "automobile_db"),
}


def get_connection():
    """Return a mysql-connector connection with autocommit OFF."""
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
    except mysql.connector.Error as err:
        if err.errno == 1045:  # Access denied (bad user/password)
            sys.exit(
                "Could not log in to MySQL as "
                f"'{DB_CONFIG['user']}'@'{DB_CONFIG['host']}'.\n"
                "This almost always means DB_PASSWORD isn't set to your "
                "actual MySQL root password. Create a '.env' file in the "
                "project root (copy .env.example) and fill in DB_PASSWORD, "
                "or export it directly in your shell. See README.md."
            )
        elif err.errno == 1049:  # Unknown database
            sys.exit(
                f"Database '{DB_CONFIG['database']}' doesn't exist yet.\n"
                "Run: mysql -u root -p -e \"CREATE DATABASE "
                f"{DB_CONFIG['database']}\" then `python db.py`."
            )
        elif err.errno == 2003:  # Can't connect to server
            sys.exit(
                f"Could not reach MySQL at {DB_CONFIG['host']}.\n"
                "Make sure the MySQL server is running "
                "(e.g. `brew services start mysql`, "
                "`sudo systemctl start mysql`, or your Docker container)."
            )
        raise
    # Autocommit off lets multi-write operations (e.g. recording a
    # sale AND clearing a vehicle's current_dealer_id) be wrapped in
    # one commit()/rollback() pair so they succeed or fail together.
    conn.autocommit = False
    return conn


def dict_cursor(conn):
    """Return a cursor whose rows come back as dicts, not tuples."""
    # Lets query code read row["sale_price"] instead of row[4], and
    # lets Jinja templates use row.sale_price-style dot access.
    return conn.cursor(dictionary=True)


def _strip_sql_comments(script):
    """Strip '--' line comments out of a SQL script."""
    # mysql-connector's execute() only runs one statement at a time,
    # so schema.sql has to be split into statements on ';' ourselves.
    # Comments need to go first or a comment-only line could throw
    # off that split.
    kept_lines = [
        line for line in script.splitlines()
        if not line.strip().startswith("--")
    ]
    return "\n".join(kept_lines)


def init_db(schema_path=None):
    """(Re)build the schema from schema.sql against an existing database."""
    if schema_path is None:
        schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")

    conn = get_connection()
    cur = conn.cursor()

    with open(schema_path, "r") as f:
        raw_script = f.read()

    cleaned = _strip_sql_comments(raw_script)
    statements = [s.strip() for s in cleaned.split(";") if s.strip()]

    # schema.sql's own DROP TABLE IF EXISTS ... at the top makes this
    # safe to rerun for a clean rebuild while iterating on the design.
    for stmt in statements:
        cur.execute(stmt)

    conn.commit()
    cur.close()
    conn.close()
    print(f"Schema (re)built in database '{DB_CONFIG['database']}'.")


if __name__ == "__main__":
    # Running `python db.py` directly rebuilds the schema.
    init_db()
