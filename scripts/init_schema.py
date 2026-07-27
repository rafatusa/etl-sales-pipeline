#!/usr/bin/env python3
"""
Database schema initialisation — run once by the CI configure stage.

Creates the 'salesdb' database (if absent) and the 'sales_records' table
with a UNIQUE index on (order_id, product_id) for idempotent upserts.

Usage:
    python scripts/init_schema.py \\
        --host <rds-endpoint> --db salesdb --user etladmin --password <pwd>
"""

import argparse
import sys
import time

import psycopg2
from psycopg2 import sql
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Initialise ETL pipeline PostgreSQL schema")
    parser.add_argument("--host", required=True, help="RDS endpoint hostname")
    parser.add_argument("--db", default="salesdb", help="Database name (default: salesdb)")
    parser.add_argument("--user", required=True, help="Database username")
    parser.add_argument("--password", required=True, help="Database password")
    parser.add_argument("--port", type=int, default=5432, help="PostgreSQL port (default: 5432)")
    return parser.parse_args()


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sales_records (
    id              SERIAL PRIMARY KEY,
    order_id        VARCHAR(50)    NOT NULL,
    customer_id     VARCHAR(50)    NOT NULL,
    product_id      VARCHAR(50)    NOT NULL,
    product_name    VARCHAR(255)   NOT NULL,
    category        VARCHAR(100),
    quantity        INTEGER        NOT NULL CHECK (quantity > 0),
    unit_price      NUMERIC(10, 2) NOT NULL CHECK (unit_price >= 0),
    total_price     NUMERIC(10, 2) NOT NULL CHECK (total_price >= 0),
    order_date      DATE           NOT NULL,
    region          VARCHAR(100),
    source_file     VARCHAR(500),
    processed_at    TIMESTAMP      NOT NULL DEFAULT NOW()
);

-- Unique index for idempotent upserts: same (order_id, product_id) → skip
CREATE UNIQUE INDEX IF NOT EXISTS uix_sales_order_product
    ON sales_records (order_id, product_id);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_sales_customer    ON sales_records (customer_id);
CREATE INDEX IF NOT EXISTS idx_sales_order_date  ON sales_records (order_date);
CREATE INDEX IF NOT EXISTS idx_sales_region      ON sales_records (region);
CREATE INDEX IF NOT EXISTS idx_sales_category    ON sales_records (category);
CREATE INDEX IF NOT EXISTS idx_sales_source_file ON sales_records (source_file);
"""


def wait_for_db(host: str, port: int, user: str, password: str, retries: int = 10) -> None:
    """Poll until the RDS instance is accepting connections."""
    for attempt in range(1, retries + 1):
        try:
            conn = psycopg2.connect(
                host=host, port=port, dbname="postgres",
                user=user, password=password,
                connect_timeout=10, sslmode="require",
            )
            conn.close()
            print(f"[init_schema] Database reachable after {attempt} attempt(s)")
            return
        except psycopg2.OperationalError as exc:
            if attempt == retries:
                raise
            print(f"[init_schema] Waiting for DB (attempt {attempt}/{retries}): {exc}")
            time.sleep(10)


def main() -> None:
    args = parse_args()

    print(f"[init_schema] Connecting to {args.host}:{args.port} as {args.user}")
    wait_for_db(args.host, args.port, args.user, args.password)

    # Connect to the default 'postgres' db to create salesdb if needed
    conn = psycopg2.connect(
        host=args.host, port=args.port, dbname="postgres",
        user=args.user, password=args.password,
        connect_timeout=10, sslmode="require",
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)

    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (args.db,))
        if not cur.fetchone():
            cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(args.db)))
            print(f"[init_schema] Created database '{args.db}'")
        else:
            print(f"[init_schema] Database '{args.db}' already exists — skipping create")

    conn.close()

    # Now connect to salesdb and apply schema
    conn = psycopg2.connect(
        host=args.host, port=args.port, dbname=args.db,
        user=args.user, password=args.password,
        connect_timeout=10, sslmode="require",
    )

    with conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)
    conn.close()

    print("[init_schema] Schema initialisation complete")
    print("[init_schema] Table: sales_records")
    print("[init_schema] Unique index: (order_id, product_id)")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[init_schema] FATAL: {exc}", file=sys.stderr)
        sys.exit(1)
