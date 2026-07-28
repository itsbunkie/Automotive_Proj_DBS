"""
dba_cli.py — the DBA interface.

The handout explicitly says this one can just be "SQL either via
the command line or SQL Developer" — so this file is intentionally
tiny. It's a thin REPL (read-eval-print loop) so you (the DBA) can
type raw SQL against MySQL without opening a separate `mysql`
client shell each time.

Run: python dba_cli.py
Type SQL statements, hit Enter after each full statement (no
trailing ';' needed). Type 'exit' or 'quit' to leave.
"""

from db import get_connection, dict_cursor


def main():
    conn = get_connection()
    print("DBA CLI — type SQL statements, 'exit' to quit.")
    while True:
        try:
            stmt = input("sql> ").strip().rstrip(";")
        except (EOFError, KeyboardInterrupt):
            break

        if stmt.lower() in ("exit", "quit"):
            break
        if not stmt:
            continue

        try:
            if stmt.strip().lower().startswith("select"):
                cur = dict_cursor(conn)
                cur.execute(stmt)
                rows = cur.fetchall()
                if not rows:
                    print("(no rows)")
                else:
                    print(" | ".join(rows[0].keys()))
                    for r in rows:
                        print(" | ".join(str(v) for v in r.values()))
                cur.close()
            else:
                cur = conn.cursor()
                cur.execute(stmt)
                conn.commit()
                print(f"OK ({cur.rowcount} rows affected)")
                cur.close()
        except Exception as e:
            conn.rollback()
            print(f"ERROR: {e}")

    conn.close()


if __name__ == "__main__":
    main()
