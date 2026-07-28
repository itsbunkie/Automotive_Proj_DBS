"""
queries.py — the six required client queries from the handout, each
as its own function returning rows. app.py and dba_cli.py both
import from here, so the SQL is written once and every interface
that needs, say, "top brands" (marketing report AND a quick CLI
sanity check) calls the same function instead of drifting out of
sync with a copy-pasted variant.

Every function follows the same shape: open (or reuse) a
connection, get a dict_cursor so rows come back as column_name ->
value mappings, run one parameterized query, return the rows.
Passing values through the second argument to cur.execute() (never
by string-formatting them into the SQL) is what keeps this code
safe from SQL injection — worth calling out explicitly since a
customer-facing form (see app.py's /search and /locator) is exactly
the kind of input this matters for.
"""

from db import get_connection, dict_cursor


# ------------------------------------------------------------
# QUERY 1: Top 2 brands by dollar amount sold, past year
# ------------------------------------------------------------
def top_brands_by_dollar_sales(conn=None, limit=2):
    """
    Strategy: sales -> vehicles (get model_id) -> models (get
    brand_id) -> brands (get name). Filter sale_date to the last
    365 days. SUM(sale_price) grouped by brand, ordered descending,
    LIMIT 2.
    """
    own_conn = conn is None
    if own_conn:
        conn = get_connection()

    cur = dict_cursor(conn)
    sql = """
        SELECT b.brand_name,
               SUM(s.sale_price) AS total_dollars,
               COUNT(*) AS units_sold
        FROM sales s
        JOIN vehicles v ON s.vin = v.vin
        JOIN models m ON v.model_id = m.model_id
        JOIN brands b ON m.brand_id = b.brand_id
        WHERE s.sale_date >= CURDATE() - INTERVAL 365 DAY
        GROUP BY b.brand_name
        ORDER BY total_dollars DESC
        LIMIT %s
    """
    cur.execute(sql, (limit,))
    result = cur.fetchall()
    cur.close()

    if own_conn:
        conn.close()
    return result


# ------------------------------------------------------------
# QUERY 2: Top 2 brands by UNIT sales, past year
# ------------------------------------------------------------
def top_brands_by_unit_sales(conn=None, limit=2):
    """
    Same join chain as query 1, but ranked by COUNT(*) instead of
    SUM(sale_price). The two rankings can legitimately disagree — a
    brand selling fewer, pricier cars can win on dollars while
    losing on units — which is worth a sentence in the writeup
    rather than something to "fix."
    """
    own_conn = conn is None
    if own_conn:
        conn = get_connection()

    cur = dict_cursor(conn)
    sql = """
        SELECT b.brand_name,
               COUNT(*) AS units_sold,
               SUM(s.sale_price) AS total_dollars
        FROM sales s
        JOIN vehicles v ON s.vin = v.vin
        JOIN models m ON v.model_id = m.model_id
        JOIN brands b ON m.brand_id = b.brand_id
        WHERE s.sale_date >= CURDATE() - INTERVAL 365 DAY
        GROUP BY b.brand_name
        ORDER BY units_sold DESC
        LIMIT %s
    """
    cur.execute(sql, (limit,))
    result = cur.fetchall()
    cur.close()

    if own_conn:
        conn.close()
    return result


# ------------------------------------------------------------
# QUERY 3: Sales trends by brand, year/month/week,
#          broken out by gender, then by income range
# ------------------------------------------------------------
def sales_trends_by_brand(conn=None, group_by="month"):
    """
    Returns THREE separate result sets rather than one giant
    cross-tab: (a) trend by brand + time bucket, (b) the same
    broken out by gender, (c) the same broken out by income range.
    The handout's phrasing — "break these data out by gender...
    and then by income range" — reads as sequential breakdowns, and
    three narrow tables are much easier for a marketing user to
    actually read than one wide one with every dimension crammed
    into a single row.

    group_by selects the time bucket granularity via MySQL's
    DATE_FORMAT():
      'year'  -> DATE_FORMAT(sale_date, '%Y')     e.g. '2025'
      'month' -> DATE_FORMAT(sale_date, '%Y-%m')  e.g. '2025-04'
      'week'  -> DATE_FORMAT(sale_date, '%Y-%u')  e.g. '2025-14'
    """
    own_conn = conn is None
    if own_conn:
        conn = get_connection()

    bucket_expr = {
        "year": "DATE_FORMAT(s.sale_date, '%Y')",
        "month": "DATE_FORMAT(s.sale_date, '%Y-%m')",
        "week": "DATE_FORMAT(s.sale_date, '%Y-%u')",
    }[group_by]

    cur = dict_cursor(conn)

    # (a) overall trend, by brand and time bucket
    cur.execute(f"""
        SELECT b.brand_name, {bucket_expr} AS time_bucket,
               COUNT(*) AS units_sold, SUM(s.sale_price) AS total_dollars
        FROM sales s
        JOIN vehicles v ON s.vin = v.vin
        JOIN models m ON v.model_id = m.model_id
        JOIN brands b ON m.brand_id = b.brand_id
        GROUP BY b.brand_name, time_bucket
        ORDER BY b.brand_name, time_bucket
    """)
    overall = cur.fetchall()

    # (b) same, broken out by customer gender
    cur.execute(f"""
        SELECT b.brand_name, {bucket_expr} AS time_bucket, c.gender,
               COUNT(*) AS units_sold, SUM(s.sale_price) AS total_dollars
        FROM sales s
        JOIN vehicles v ON s.vin = v.vin
        JOIN models m ON v.model_id = m.model_id
        JOIN brands b ON m.brand_id = b.brand_id
        JOIN customers c ON s.customer_id = c.customer_id
        GROUP BY b.brand_name, time_bucket, c.gender
        ORDER BY b.brand_name, time_bucket
    """)
    by_gender = cur.fetchall()

    # (c) same, broken out by income range (bucketed with CASE
    # since annual_income is continuous — grouping on the raw
    # dollar figure would give one group per distinct income)
    cur.execute(f"""
        SELECT b.brand_name, {bucket_expr} AS time_bucket,
               CASE
                 WHEN c.annual_income < 40000 THEN 'under_40k'
                 WHEN c.annual_income < 80000 THEN '40k_80k'
                 WHEN c.annual_income < 150000 THEN '80k_150k'
                 ELSE '150k_plus'
               END AS income_range,
               COUNT(*) AS units_sold, SUM(s.sale_price) AS total_dollars
        FROM sales s
        JOIN vehicles v ON s.vin = v.vin
        JOIN models m ON v.model_id = m.model_id
        JOIN brands b ON m.brand_id = b.brand_id
        JOIN customers c ON s.customer_id = c.customer_id
        GROUP BY b.brand_name, time_bucket, income_range
        ORDER BY b.brand_name, time_bucket
    """)
    by_income = cur.fetchall()

    cur.close()
    if own_conn:
        conn.close()
    return {"overall": overall, "by_gender": by_gender, "by_income": by_income}


# ------------------------------------------------------------
# QUERY 4: Defective Getrag transmissions -> affected VINs + customers
# ------------------------------------------------------------
def find_affected_vehicles(conn=None, supplier_name="Getrag",
                            part_name="Transmission",
                            start_date="2023-01-01", end_date="2026-12-31"):
    """
    parts -> suppliers narrows to the defective part/supplier pair;
    vehicle_parts (not model_parts) is what pins down WHICH exact
    VIN got one and WHEN, so install_date can be filtered against
    the recall window. sales/customers are LEFT JOINed rather than
    inner-joined on purpose: an inner join would silently drop any
    affected vehicle still sitting unsold in a dealer's inventory,
    which is exactly the kind of car a real recall still needs to
    catch even though it has no customer to notify yet.
    """
    own_conn = conn is None
    if own_conn:
        conn = get_connection()

    cur = dict_cursor(conn)
    sql = """
        SELECT v.vin, vp.install_date, p.supplying_plant_id,
               c.full_name AS customer_name, c.phone AS customer_phone,
               s.sale_date
        FROM parts p
        JOIN suppliers sup ON p.supplier_id = sup.supplier_id
        JOIN vehicle_parts vp ON vp.part_id = p.part_id
        JOIN vehicles v ON vp.vin = v.vin
        LEFT JOIN sales s ON s.vin = v.vin
        LEFT JOIN customers c ON s.customer_id = c.customer_id
        WHERE sup.supplier_name = %s
          AND p.part_name = %s
          AND vp.install_date BETWEEN %s AND %s
        ORDER BY vp.install_date
    """
    cur.execute(sql, (supplier_name, part_name, start_date, end_date))
    result = cur.fetchall()
    cur.close()

    if own_conn:
        conn.close()
    return result


# ------------------------------------------------------------
# QUERY 5: Best month(s) for convertible sales
# ------------------------------------------------------------
def best_month_for_convertibles(conn=None):
    """
    Groups by MONTH(sale_date) rather than a year+month bucket, so
    "May" aggregates sales across every year of data instead of
    treating May-2024 and May-2025 as separate rows — that's the
    reading of "in what month(s) do convertibles sell best" that
    actually answers a seasonality question rather than a one-time
    trend question (which query 3 already covers).
    """
    own_conn = conn is None
    if own_conn:
        conn = get_connection()

    cur = dict_cursor(conn)
    sql = """
        SELECT MONTHNAME(s.sale_date) AS month_name,
               MONTH(s.sale_date) AS month_num,
               COUNT(*) AS units_sold,
               SUM(s.sale_price) AS total_dollars
        FROM sales s
        JOIN vehicles v ON s.vin = v.vin
        JOIN models m ON v.model_id = m.model_id
        WHERE m.body_style = 'convertible'
        GROUP BY month_num, month_name
        ORDER BY units_sold DESC
    """
    cur.execute(sql)
    result = cur.fetchall()
    cur.close()

    if own_conn:
        conn.close()
    return result


# ------------------------------------------------------------
# QUERY 6: Dealers with the longest average inventory hold time
# ------------------------------------------------------------
def longest_avg_inventory_time(conn=None):
    """
    DESIGN DECISION: this counts only vehicles that HAVE sold (an
    inner join to sales), so avg_days_held is a clean, fully-known
    number for every dealer in the result. The alternative — also
    counting still-unsold current inventory using
    DATEDIFF(CURDATE(), arrived_at_dealer_date) as a running total
    — would pull the average toward whatever's sitting on the lot
    RIGHT NOW rather than describing historical dealer behavior,
    and would keep changing every time this query is re-run on a
    later date even with an unchanged sales history. The handout
    doesn't specify which reading it wants ("the manager... is not
    computer literate"), so this assumption is called out here and
    in the README rather than silently baked in.
    """
    own_conn = conn is None
    if own_conn:
        conn = get_connection()

    cur = dict_cursor(conn)
    sql = """
        SELECT d.dealer_name,
               AVG(DATEDIFF(s.sale_date, v.arrived_at_dealer_date)) AS avg_days_held,
               COUNT(*) AS vehicles_sold
        FROM vehicles v
        JOIN sales s ON s.vin = v.vin
        JOIN dealers d ON v.current_dealer_id = d.dealer_id
        GROUP BY d.dealer_name
        ORDER BY avg_days_held DESC
    """
    cur.execute(sql)
    result = cur.fetchall()
    cur.close()

    if own_conn:
        conn.close()
    return result
