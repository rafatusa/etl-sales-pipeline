#!/usr/bin/env python3
"""
Database schema initialisation — run as a one-shot ECS Fargate task
by the CI configure stage (inside the VPC so it can reach private RDS).

Reads connection details from the same environment variables the ETL
container uses:
    DB_HOST      RDS endpoint hostname
    DB_PORT      PostgreSQL port (default: 5432)
    DB_NAME      Target database name (default: salesdb)
    DB_USER      Database username
    DB_PASSWORD  Database password (injected from Secrets Manager in ECS)

Local usage (with .env loaded by docker-compose or exported manually):
    export DB_HOST=localhost DB_PORT=5432 DB_NAME=salesdb \
           DB_USER=etladmin DB_PASSWORD=<pwd>
    python scripts/init_schema.py
"""

import os
import sys
import time

import psycopg2
from psycopg2 import sql
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT


def get_config() -> dict:
    """Read DB connection config from environment variables."""
    required = {"DB_HOST", "DB_USER", "DB_PASSWORD"}
    missing = required - set(os.environ)
    if missing:
        print(f"[init_schema] FATAL: missing required env vars: {', '.join(sorted(missing))}", file=sys.stderr)
        sys.exit(1)

    return {
        "host": os.environ["DB_HOST"],
        "port": int(os.environ.get("DB_PORT", "5432")),
        "dbname": os.environ.get("DB_NAME", "salesdb"),
        "user": os.environ["DB_USER"],
        "password": os.environ["DB_PASSWORD"],
    }


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

-- Unique index for idempotent upserts: same (order_id, product_id) -> skip
CREATE UNIQUE INDEX IF NOT EXISTS uix_sales_order_product
    ON sales_records (order_id, product_id);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_sales_customer    ON sales_records (customer_id);
CREATE INDEX IF NOT EXISTS idx_sales_order_date  ON sales_records (order_date);
CREATE INDEX IF NOT EXISTS idx_sales_region      ON sales_records (region);
CREATE INDEX IF NOT EXISTS idx_sales_category    ON sales_records (category);
CREATE INDEX IF NOT EXISTS idx_sales_source_file ON sales_records (source_file);
"""


def wait_for_db(cfg: dict, retries: int = 10) -> None:
    """Poll until the RDS instance is accepting connections."""
    print(f"[init_schema] Connecting to {cfg['host']}:{cfg['port']} as {cfg['user']}")
    for attempt in range(1, retries + 1):
        try:
            conn = psycopg2.connect(
                host=cfg["host"],
                port=cfg["port"],
                dbname="postgres",
                user=cfg["user"],
                password=cfg["password"],
                connect_timeout=10,
                sslmode="require",
            )
            conn.close()
            print(f"[init_schema] Database reachable after {attempt} attempt(s)")
            return
        except psycopg2.OperationalError as exc:
            if attempt == retries:
                raise
            print(f"[init_schema] Waiting for DB (attempt {attempt}/{retries}): {exc}")
            time.sleep(10)


def ensure_database(cfg: dict) -> None:
    """Create the target database if it does not already exist."""
    conn = psycopg2.connect(
        host=cfg["host"],
        port=cfg["port"],
        dbname="postgres",
        user=cfg["user"],
        password=cfg["password"],
        connect_timeout=10,
        sslmode="require",
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)

    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (cfg["dbname"],))
        if not cur.fetchone():
            cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(cfg["dbname"])))
            print(f"[init_schema] Created database '{cfg['dbname']}'")
        else:
            print(f"[init_schema] Database '{cfg['dbname']}' already exists -- skipping create")

    conn.close()


def apply_schema(cfg: dict) -> None:
    """Apply the DDL schema to the target database."""
    conn = psycopg2.connect(
        host=cfg["host"],
        port=cfg["port"],
        dbname=cfg["dbname"],
        user=cfg["user"],
        password=cfg["password"],
        connect_timeout=10,
        sslmode="require",
    )

    with conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)

    conn.close()
    print("[init_schema] Schema applied successfully")
    print("[init_schema]   Table  : sales_records")
    print("[init_schema]   Index  : uix_sales_order_product (order_id, product_id)")


def main() -> None:
    cfg = get_config()
    wait_for_db(cfg)
    ensure_database(cfg)
    apply_schema(cfg)
    print("[init_schema] Schema initialisation complete")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[init_schema] FATAL: {exc}", file=sys.stderr)
        sys.exit(1)
