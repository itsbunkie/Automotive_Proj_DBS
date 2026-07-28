"""
queries.py — the six required client queries, each as its own
function returning rows. app.py and dba_cli.py both import from
here, so the SQL is written once instead of drifting out of sync
across multiple copy-pasted versions.

Every function follows the same shape: open (or reuse) a
connection, get a dict_cursor, run one parameterized query, return
the rows. Values are always passed through cur.execute()'s second
argument rather than string-formatted into the SQL — that's what
keeps this safe from SQL injection, which matters most for the
customer-facing forms in app.py (/search and /locator).
"""

from db import get_connection, dict_cursor


def top_brands_by_dollar_sales(conn=None, limit=2):
    """Top brands by total sale_price over the last year."""
    own_conn = conn is None
    if own_conn:
        conn = get_connection()

    cur = dict_cursor(conn)
    # sales -> vehicles -> models -> brands, filtered to the last
    # 365 days, summed and ranked by dollar amount.
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


def top_brands_by_unit_sales(conn=None, limit=2):
    """Top brands by number of units sold over the last year."""
    own_conn = conn is None
    if own_conn:
        conn = get_connection()

    cur = dict_cursor(conn)
    # Same join chain as top_brands_by_dollar_sales, ranked by
    # COUNT(*) instead — the two rankings can legitimately disagree
    # if a brand sells fewer, pricier cars.
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


def sales_trends_by_brand(conn=None, group_by="month"):
    """Sales trends by brand and time bucket, plus gender/income breakdowns."""
    own_conn = conn is None
    if own_conn:
        conn = get_connection()

    # group_by picks the time bucket granularity via DATE_FORMAT().
    bucket_expr = {
        "year": "DATE_FORMAT(s.sale_date, '%Y')",
        "month": "DATE_FORMAT(s.sale_date, '%Y-%m')",
        "week": "DATE_FORMAT(s.sale_date, '%Y-%u')",
    }[group_by]

    cur = dict_cursor(conn)

    # Three separate result sets, rather than one wide cross-tab, so
    # each is easy for a marketing user to read on its own.

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

    # (c) same, broken out by income range. Bucketed with CASE since
    # annual_income is continuous — grouping on the raw dollar figure
    # would give one group per distinct income value.
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


def find_affected_vehicles(conn=None, supplier_name="Getrag",
                            part_name="Transmission",
                            start_date="2023-01-01", end_date="2026-12-31"):
    """VINs (and their customers, if sold) that received a given defective part."""
    own_conn = conn is None
    if own_conn:
        conn = get_connection()

    cur = dict_cursor(conn)
    # vehicle_parts (not model_parts) is what pins down which exact
    # VIN got the part and when, so install_date can be filtered
    # against the recall window. sales/customers are LEFT JOINed on
    # purpose: an inner join would drop any affected vehicle still
    # unsold in inventory, which a real recall still needs to catch.
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


def best_month_for_convertibles(conn=None):
    """Which calendar month(s) convertibles sell best in, across all years."""
    own_conn = conn is None
    if own_conn:
        conn = get_connection()

    cur = dict_cursor(conn)
    # Grouped by MONTH(sale_date) rather than year+month, so "May"
    # aggregates across every year instead of splitting May-2024 and
    # May-2025 into separate rows — a seasonality read rather than
    # the year-over-year trend query 3 already covers.
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


def longest_avg_inventory_time(conn=None):
    """Dealers ranked by average days between a vehicle arriving and selling."""
    own_conn = conn is None
    if own_conn:
        conn = get_connection()

    cur = dict_cursor(conn)
    # Only counts vehicles that have actually sold (inner join to
    # sales), so avg_days_held is a clean, fully-known number per
    # dealer. Including still-unsold inventory would pull the
    # average toward whatever's on the lot right now and keep
    # shifting the result on every re-run.
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
