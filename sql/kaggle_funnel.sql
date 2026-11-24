WITH first_views AS (
    SELECT user_id, session_id, MIN(event_time) AS first_view_at
    FROM events
    WHERE event_type = 'view'
    GROUP BY user_id, session_id
),
ordered_carts AS (
    SELECT v.user_id, v.session_id, MIN(c.event_time) AS first_cart_at
    FROM first_views AS v
    JOIN events AS c
      ON c.user_id = v.user_id
     AND c.session_id = v.session_id
     AND c.event_type = 'cart'
     AND c.event_time >= v.first_view_at
    GROUP BY v.user_id, v.session_id
),
ordered_purchases AS (
    SELECT c.user_id, c.session_id
    FROM ordered_carts AS c
    WHERE EXISTS (
        SELECT 1
        FROM events AS p
        WHERE p.user_id = c.user_id
          AND p.session_id = c.session_id
          AND p.event_type = 'purchase'
          AND p.event_time >= c.first_cart_at
    )
),
counts AS (
    SELECT
        (SELECT COUNT(*) FROM first_views) AS viewed,
        (SELECT COUNT(*) FROM ordered_carts) AS added,
        (SELECT COUNT(*) FROM ordered_purchases) AS purchased
)
SELECT 'view' AS step, viewed AS sessions, NULL AS conversion_pct FROM counts
UNION ALL
SELECT 'cart', added, ROUND(100.0 * added / NULLIF(viewed, 0), 2) FROM counts
UNION ALL
SELECT 'purchase', purchased, ROUND(100.0 * purchased / NULLIF(added, 0), 2)
FROM counts;
