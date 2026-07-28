"""
db.py -- single place that knows how to talk to the database.

Every other file (queries.py, app.py, dba_cli.py, generate_data.py)
imports get_connection()/dict_cursor() from here instead of opening
its own connection. That way, if a connection detail ever changes
(host, credentials, even the database library itself), it changes
in ONE file, not five.

This project targets MySQL specifically -- schema.sql relies on
AUTO_INCREMENT / ENGINE=InnoDB syntax, queries.py uses %s-style
placeholders and functions like DATE_FORMAT()/DATEDIFF(), and
requirements.txt pins mysql-connector-python -- so this file is
built directly around mysql.connector rather than a
database-agnostic wrapper.
"""

import os
import mysql.connector

# ------------------------------------------------------------
# CONNECTION CONFIG
# Pulled from environment variables first (so grader/DBA can point
# this at any MySQL instance without editing code), falling back to
# reasonable local defaults matching the README's setup steps.
# ------------------------------------------------------------
DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "localhost"),
    "user": os.environ.get("DB_USER", "root"),
    "password": os.environ.get("DB_PASSWORD", ""),
    "database": os.environ.get("DB_NAME", "automobile_db"),
}


def get_connection():
    """
    Return a mysql-connector connection with autocommit OFF.

    Keeping autocommit off is what makes the concurrency
    requirement (handout item 6) satisfiable: any place the code
    performs multiple related writes -- e.g. recording a sale AND
    clearing a vehicle's current_dealer_id -- can wrap both in one
    conn.commit()/conn.rollback() pair so they succeed or fail
    together instead of leaving the database in a half-updated
    state if something goes wrong mid-transaction.
    """
    conn = mysql.connector.connect(**DB_CONFIG)
    conn.autocommit = False
    return conn


def dict_cursor(conn):
    """
    Return a cursor whose fetchall()/fetchone() rows come back as
    dicts (column_name -> value) rather than plain tuples. Every
    query function in queries.py and every ad-hoc query in app.py
    uses this so results can be read as row["sale_price"] in
    Python and row.sale_price-style dot access in Jinja templates,
    instead of brittle positional indexing like row[4].
    """
    return conn.cursor(dictionary=True)


def _strip_sql_comments(script):
    """
    Remove '--' line comments before splitting the schema file on
    ';'. mysql-connector's cursor.execute() only runs ONE statement
    at a time (unlike sqlite3's executescript()), so schema.sql has
    to be split into individual statements ourselves. If we split
    on raw ';' without stripping comments first, a statement whose
    leading lines are comment-only would get misidentified -- this
    keeps the split reliable regardless of how schema.sql is
    formatted.
    """
    kept_lines = [
        line for line in script.splitlines()
        if not line.strip().startswith("--")
    ]
    return "\n".join(kept_lines)


def init_db(schema_path=None):
    """
    (Re)build the schema from schema.sql against an EXISTING
    database (per the handout's setup: `CREATE DATABASE
    automobile_db;` is a manual, one-time step -- this function
    only (re)creates the tables inside it, matching schema.sql's
    own DROP TABLE IF EXISTS ... at the top for a clean rebuild
    while iterating on the design).
    """
    if schema_path is None:
        schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")

    conn = mysql.connector.connect(**DB_CONFIG)
    cur = conn.cursor()

    with open(schema_path, "r") as f:
        raw_script = f.read()

    cleaned = _strip_sql_comments(raw_script)
    statements = [s.strip() for s in cleaned.split(";") if s.strip()]

    for stmt in statements:
        cur.execute(stmt)

    conn.commit()
    cur.close()
    conn.close()
    print(f"Schema (re)built in database '{DB_CONFIG['database']}'.")


if __name__ == "__main__":
    # Running `python db.py` directly rebuilds the schema.
    init_db()
