import argparse
import csv
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parent
EVENT_TYPES = {"view", "cart", "purchase"}
REQUIRED_COLUMNS = {"user_id", "user_session", "event_time", "event_type"}


def load_events(connection, source):
    loaded = 0
    missing_session = 0
    batch = []
    insert = "INSERT INTO events VALUES (?, ?, ?, ?)"
    with source.open(encoding="utf-8-sig", newline="") as stream:
        rows = csv.DictReader(stream)
        missing_columns = REQUIRED_COLUMNS - set(rows.fieldnames or [])
        if missing_columns:
            raise ValueError(f"CSV is missing columns: {', '.join(sorted(missing_columns))}")

        for row in rows:
            if row["event_type"] not in EVENT_TYPES:
                continue
            user_id = (row["user_id"] or "").strip()
            session_id = (row["user_session"] or "").strip()
            if not user_id or not session_id:
                missing_session += 1
                continue

            # The source records UTC timestamps in YYYY-MM-DD HH:MM:SS format.
            timestamp = (row["event_time"] or "").strip().removesuffix(" UTC")
            if len(timestamp) != 19:
                raise ValueError(f"Invalid event_time on CSV line {rows.line_num}")
            batch.append((user_id, session_id, row["event_type"], timestamp))
            loaded += 1
            if len(batch) == 10_000:
                connection.executemany(insert, batch)
                batch.clear()

    connection.executemany(insert, batch)
    return loaded, missing_session


def main():
    parser = argparse.ArgumentParser(description="Build an ordered Kaggle session funnel.")
    parser.add_argument("input", type=Path, help="Extracted monthly Kaggle events CSV")
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "kaggle_funnel.csv")
    args = parser.parse_args()
    sql = (ROOT / "sql" / "kaggle_funnel.sql").read_text(encoding="utf-8")

    with TemporaryDirectory() as work_dir:
        connection = sqlite3.connect(Path(work_dir) / "events.sqlite")
        try:
            connection.execute("""
                CREATE TABLE events (
                    user_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    event_time TEXT NOT NULL
                )
            """)
            loaded, missing_session = load_events(connection, args.input)
            connection.execute("""
                CREATE INDEX event_lookup
                ON events (event_type, user_id, session_id, event_time)
            """)
            result = connection.execute(sql)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow(column[0] for column in result.description)
                writer.writerows(result)
        finally:
            connection.close()

    print(f"Loaded {loaded:,} events. Skipped {missing_session:,} with no session or user.")
    print(f"Report: {args.output}")


if __name__ == "__main__":
    main()
