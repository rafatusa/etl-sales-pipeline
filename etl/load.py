"""
Load stage — upsert clean records into PostgreSQL using SQLAlchemy.

Idempotency guarantee:
  - Table has a UNIQUE index on (order_id, product_id)
  - Insert uses INSERT ... ON CONFLICT (order_id, product_id) DO NOTHING
  - Re-processing the same CSV file produces zero net-new rows (no duplicates)

Batch inserts: configurable batch_size (default 500) to avoid memory spikes
on large datasets while keeping round-trips low.
"""

import time
from typing import Optional

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from etl.config import Config
from etl.logger import get_logger

logger = get_logger(__name__)

# Column name mapping: DataFrame (PascalCase CSV) -> DB (snake_case)
COLUMN_MAP = {
    "OrderID": "order_id",
    "CustomerID": "customer_id",
    "ProductID": "product_id",
    "ProductName": "product_name",
    "Category": "category",
    "Quantity": "quantity",
    "UnitPrice": "unit_price",
    "TotalPrice": "total_price",
    "OrderDate": "order_date",
    "Region": "region",
    "source_file": "source_file",
}

UPSERT_SQL = text("""
    INSERT INTO sales_records
        (order_id, customer_id, product_id, product_name, category,
         quantity, unit_price, total_price, order_date, region, source_file)
    VALUES
        (:order_id, :customer_id, :product_id, :product_name, :category,
         :quantity, :unit_price, :total_price, :order_date, :region, :source_file)
    ON CONFLICT (order_id, product_id) DO NOTHING
""")


def get_engine(config: Config) -> Engine:
    """Create SQLAlchemy engine with connection pool settings for a batch job."""
    return create_engine(
        config.db_url,
        pool_size=5,
        max_overflow=2,
        pool_timeout=30,
        pool_recycle=1800,
        connect_args={"connect_timeout": 10},
    )


def _insert_batch(
    connection,
    batch: list[dict],
    batch_num: int,
) -> tuple[int, int]:
    """Insert one batch; return (attempted, inserted) counts."""
    attempted = len(batch)
    result = connection.execute(UPSERT_SQL, batch)
    inserted = result.rowcount
    skipped = attempted - inserted
    logger.info(
        f"Batch {batch_num}: {inserted} inserted, {skipped} skipped (already exist)",
        extra={
            "stage": "load",
            "batch": batch_num,
            "inserted": inserted,
            "skipped": skipped,
        },
    )
    return attempted, inserted


def run(
    clean_df: pd.DataFrame,
    config: Config,
    engine: Optional[Engine] = None,
) -> tuple[int, int]:
    """
    Load clean_df into sales_records with idempotent upsert.

    Returns:
        (total_inserted, total_skipped)
    """
    if clean_df.empty:
        logger.info(
            "No clean rows to load — skipping load stage",
            extra={"stage": "load"},
        )
        return 0, 0

    if engine is None:
        engine = get_engine(config)

    # Rename columns to match DB schema
    df = clean_df.rename(columns=COLUMN_MAP)
    required_cols = list(COLUMN_MAP.values())
    df = df[[c for c in required_cols if c in df.columns]]

    rows = df.to_dict(orient="records")
    total_rows = len(rows)
    total_inserted = 0
    total_skipped = 0

    logger.info(
        f"Loading {total_rows} rows in batches of {config.batch_size}",
        extra={
            "stage": "load",
            "total_rows": total_rows,
            "batch_size": config.batch_size,
        },
    )

    start_time = time.monotonic()
    batch_num = 0

    with engine.begin() as conn:
        for batch_start in range(0, total_rows, config.batch_size):
            batch = rows[batch_start : batch_start + config.batch_size]
            batch_num += 1
            attempted, inserted = _insert_batch(conn, batch, batch_num)
            total_inserted += inserted
            total_skipped += attempted - inserted

    elapsed = time.monotonic() - start_time
    logger.info(
        "Load stage complete",
        extra={
            "stage": "load",
            "event": "load_complete",
            "total_rows": total_rows,
            "inserted": total_inserted,
            "skipped": total_skipped,
            "batches": batch_num,
            "duration_seconds": round(elapsed, 2),
        },
    )

    return total_inserted, total_skipped
