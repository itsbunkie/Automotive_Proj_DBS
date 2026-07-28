"""
app.py — Flask web application implementing 3 of the 4 required
interfaces:

  1. DBA interface       -> not here, see dba_cli.py
  2. Vehicle locator      -> /locator          (dealer-facing)
  3. Customer web search  -> /search            (customer-facing)
  4. Marketing/OLAP       -> /marketing         (reports)

Ad-hoc SQL written directly here (/locator and /search aren't
among queries.py's required six) still uses dict_cursor(conn) the
same way queries.py does, so results come back as dicts a Jinja
template can read with r.field_name.
"""

from flask import Flask, render_template, request
from db import get_connection, dict_cursor
import queries

app = Flask(__name__)


@app.route("/")
def home():
    """Landing page linking to the three web interfaces."""
    return render_template("home.html")


@app.route("/locator", methods=["GET", "POST"])
def locator():
    # GET just renders the empty form; the query only runs on POST,
    # so results stays None until a dealer actually submits.
    results = None
    if request.method == "POST":
        brand = request.form.get("brand", "").strip()
        model = request.form.get("model", "").strip()
        color = request.form.get("color", "").strip()
        body_style = request.form.get("body_style", "").strip()

        conn = get_connection()
        cur = dict_cursor(conn)

        # Only UNSOLD vehicles are a valid locator match — a car
        # already in `sales` isn't available to point a customer
        # toward, so it's excluded with a NOT IN subquery.
        sql = """
            SELECT v.vin, m.model_name, v.color, v.asking_price,
                   d.dealer_name, d.address AS dealer_address
            FROM vehicles v
            JOIN models m ON v.model_id = m.model_id
            JOIN brands b ON m.brand_id = b.brand_id
            LEFT JOIN dealers d ON v.current_dealer_id = d.dealer_id
            WHERE v.vin NOT IN (SELECT vin FROM sales)
        """
        # Each field is optional, so the WHERE clause and its params
        # list grow together, in lockstep, only for fields the dealer
        # actually filled in — an empty field means "don't filter on
        # this", not "match empty string".
        params = []
        if brand:
            sql += " AND b.brand_name LIKE %s"
            params.append(f"%{brand}%")
        if model:
            sql += " AND m.model_name LIKE %s"
            params.append(f"%{model}%")
        if color:
            sql += " AND v.color LIKE %s"
            params.append(f"%{color}%")
        if body_style:
            sql += " AND m.body_style LIKE %s"
            params.append(f"%{body_style}%")
        sql += " LIMIT 50"

        cur.execute(sql, tuple(params))
        results = cur.fetchall()

        # Log the inquiry itself (not the results) so marketing can
        # later see WHAT dealers keep searching for, independent of
        # whether the search happened to find a match.
        log_cur = conn.cursor()
        log_cur.execute(
            """INSERT INTO locator_inquiries (brand, model, color, body_style)
               VALUES (%s, %s, %s, %s)""",
            (brand or None, model or None, color or None, body_style or None),
        )
        conn.commit()

        cur.close()
        log_cur.close()
        conn.close()

    return render_template("locator.html", results=results)


@app.route("/search", methods=["GET", "POST"])
def search():
    # Customer-facing search: unsold inventory only, priced at
    # asking_price rather than sale_price since a car that hasn't
    # sold has no sale_price yet.
    results = None
    if request.method == "POST":
        brand = request.form.get("brand", "").strip()
        body_style = request.form.get("body_style", "").strip()
        max_price = request.form.get("max_price", "").strip()

        conn = get_connection()
        cur = dict_cursor(conn)
        sql = """
            SELECT m.model_name, v.color, v.asking_price, d.dealer_name
            FROM vehicles v
            JOIN models m ON v.model_id = m.model_id
            JOIN brands b ON m.brand_id = b.brand_id
            LEFT JOIN dealers d ON v.current_dealer_id = d.dealer_id
            WHERE v.vin NOT IN (SELECT vin FROM sales)
        """
        params = []
        if brand:
            sql += " AND b.brand_name LIKE %s"
            params.append(f"%{brand}%")
        if body_style:
            sql += " AND m.body_style LIKE %s"
            params.append(f"%{body_style}%")
        if max_price:
            sql += " AND v.asking_price <= %s"
            params.append(max_price)
        sql += " ORDER BY v.asking_price LIMIT 50"

        cur.execute(sql, tuple(params))
        results = cur.fetchall()
        cur.close()
        conn.close()

    return render_template("search.html", results=results)


@app.route("/marketing")
def marketing():
    # group_by is arbitrary query-string input, and queries.py keys
    # a dict on it to pick a DATE_FORMAT() expression — an unchecked
    # value would KeyError instead of falling back cleanly, so it's
    # whitelisted here before ever reaching that lookup.
    group_by = request.args.get("group_by", "month")
    if group_by not in ("year", "month", "week"):
        group_by = "month"

    conn = get_connection()
    top_dollar = queries.top_brands_by_dollar_sales(conn)
    top_units = queries.top_brands_by_unit_sales(conn)
    trends = queries.sales_trends_by_brand(conn, group_by=group_by)
    recall = queries.find_affected_vehicles(conn)
    conv_month = queries.best_month_for_convertibles(conn)
    inventory = queries.longest_avg_inventory_time(conn)
    conn.close()
    return render_template(
        "marketing.html",
        top_dollar=top_dollar,
        top_units=top_units,
        trends=trends,
        group_by=group_by,
        recall=recall,
        conv_month=conv_month,
        inventory=inventory,
    )
@app.route("/add-sale", methods=["GET", "POST"])
def add_sale():
    message = None
    if request.method == "POST":
        vin = request.form.get("vin").strip()
        dealer_id = request.form.get("dealer_id")
        customer_id = request.form.get("customer_id")
        sale_date = request.form.get("sale_date")
        sale_price = request.form.get("sale_price")

        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO sales (vin, dealer_id, customer_id, sale_date, sale_price)
                   VALUES (%s, %s, %s, %s, %s)""",
                (vin, dealer_id, customer_id, sale_date, sale_price)
            )
            # locator/search treat a vehicle as unsold via NOT IN
            # (SELECT vin FROM sales); the row just inserted there
            # already makes that true, so this only needs to drop
            # the now-stale dealer assignment for consistency.
            cur.execute("UPDATE vehicles SET current_dealer_id = NULL WHERE vin = %s", (vin,))
            conn.commit()
            message = f"Success: Sale recorded for VIN {vin}!"
        except Exception as e:
            conn.rollback()
            message = f"Error recording sale: {e}"
        finally:
            cur.close()
            conn.close()

    return render_template("add_sale.html", message=message)


if __name__ == "__main__":
    app.run(debug=True)
