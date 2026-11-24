import csv
import sqlite3
from pathlib import Path

REPORTS = Path(__file__).resolve().parent / "reports"
REPORTS.mkdir(exist_ok=True)

connection = sqlite3.connect(":memory:")
connection.executescript("""
    CREATE TABLE carts (
        cart_id INTEGER PRIMARY KEY,
        checkout_started INTEGER NOT NULL
    );
    CREATE TABLE attempts (
        cart_id INTEGER NOT NULL,
        attempt_no INTEGER NOT NULL,
        elapsed_seconds INTEGER NOT NULL,
        outcome TEXT NOT NULL,
        PRIMARY KEY (cart_id, attempt_no)
    );
""")

connection.executemany(
    "INSERT INTO carts VALUES (?, ?)",
    ((cart_id, int(cart_id <= 800)) for cart_id in range(1, 1001)),
)

first_attempt_groups = [
    (1, 450, "confirmed"),
    (451, 540, "delivery_price_changed"),
    (541, 575, "payment_failed"),
    (576, 600, "technical_error"),
]
for start, end, outcome in first_attempt_groups:
    connection.executemany(
        "INSERT INTO attempts VALUES (?, 1, 0, ?)",
        ((cart_id, outcome) for cart_id in range(start, end + 1)),
    )

retry_groups = [
    (451, 492, 480, "delivery_price_changed"),
    (541, 560, 554, "payment_failed"),
    (576, 590, 586, "technical_error"),
]
for start, end, last_success, failure in retry_groups:
    connection.executemany(
        "INSERT INTO attempts VALUES (?, 2, 120, ?)",
        (
            (cart_id, "confirmed" if cart_id <= last_success else failure)
            for cart_id in range(start, end + 1)
        ),
    )

cart_summary = """
    WITH outcomes AS (
        SELECT
            cart_id,
            MAX(CASE WHEN attempt_no = 1 THEN outcome END) AS first_outcome,
            MAX(CASE WHEN attempt_no > 1 THEN 1 ELSE 0 END) AS retried,
            MAX(CASE WHEN outcome = 'confirmed' THEN 1 ELSE 0 END) AS ordered
        FROM attempts
        WHERE elapsed_seconds BETWEEN 0 AND 600
        GROUP BY cart_id
    )
"""
queries = {
    "funnel": """
        SELECT COUNT(*) AS opened, SUM(c.checkout_started) AS checkout_started,
               COUNT(o.cart_id) AS attempted, SUM(o.ordered) AS ordered
        FROM carts AS c
        LEFT JOIN outcomes AS o ON o.cart_id = c.cart_id
    """,
    "failure_breakdown": """
        SELECT first_outcome, COUNT(*) AS users, SUM(retried) AS retried,
               SUM(ordered) AS ordered, ROUND(100.0 * AVG(ordered), 1) AS order_pct
        FROM outcomes
        WHERE first_outcome <> 'confirmed'
        GROUP BY first_outcome
        ORDER BY users DESC
    """,
}

for filename, query in queries.items():
    result = connection.execute(cart_summary + query)
    with (REPORTS / f"synthetic_{filename}.csv").open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(column[0] for column in result.description)
        writer.writerows(result)
connection.close()
