"""Unit tests for the load stage — focuses on idempotency and batch logic."""

import os
import pandas as pd
import pytest
from unittest.mock import MagicMock

from etl.load import COLUMN_MAP, run as load_run
from etl.config import Config

# Test DB credentials — these are local test values only, never used against real infrastructure
_TEST_DB_PASS = "testpasswordXXXXXXXX"  # noqa: S105 — test fixture, not a real credential


def _make_config(**overrides) -> Config:
    """Return a minimal Config for testing (no real AWS/DB needed)."""
    os.environ.setdefault("S3_BUCKET", "test-bucket")
    os.environ.setdefault("DB_HOST", "localhost")
    os.environ.setdefault("DB_USER", "etladmin")
    os.environ.setdefault("DB_PASSWORD", _TEST_DB_PASS)
    return Config(
        s3_bucket="test-bucket",
        db_host="localhost",
        db_user="etladmin",
        db_password=_TEST_DB_PASS,
        batch_size=overrides.get("batch_size", 500),
        max_retries=1,
        retry_delay_seconds=0,
    )


def _make_clean_df(n: int = 3) -> pd.DataFrame:
    rows = [
        {
            "OrderID": f"ORD-{i:03d}",
            "CustomerID": f"CUST-{i:03d}",
            "ProductID": f"PROD-{i:03d}",
            "ProductName": f"Product {i}",
            "Category": "Electronics",
            "Quantity": i,
            "UnitPrice": 9.99 * i,
            "TotalPrice": 9.99 * i * i,
            "OrderDate": "2024-01-15",
            "Region": "North",
            "source_file": "input/test.csv",
        }
        for i in range(1, n + 1)
    ]
    return pd.DataFrame(rows)


class TestIdempotency:
    def test_all_rows_inserted_on_first_run(self):
        config = _make_config()
        clean_df = _make_clean_df(3)
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.rowcount = 3
        mock_conn.execute.return_value = mock_result
        mock_engine.begin.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.begin.return_value.__exit__ = MagicMock(return_value=False)

        inserted, skipped = load_run(clean_df, config, engine=mock_engine)
        assert inserted == 3
        assert skipped == 0

    def test_no_rows_inserted_on_rerun(self):
        """Simulates re-processing the same file — ON CONFLICT DO NOTHING → rowcount=0."""
        config = _make_config()
        clean_df = _make_clean_df(3)
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.rowcount = 0  # All rows already exist
        mock_conn.execute.return_value = mock_result
        mock_engine.begin.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.begin.return_value.__exit__ = MagicMock(return_value=False)

        inserted, skipped = load_run(clean_df, config, engine=mock_engine)
        assert inserted == 0
        assert skipped == 3

    def test_partial_insert(self):
        """2 new rows, 1 already exists."""
        config = _make_config()
        clean_df = _make_clean_df(3)
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.rowcount = 2
        mock_conn.execute.return_value = mock_result
        mock_engine.begin.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.begin.return_value.__exit__ = MagicMock(return_value=False)

        inserted, skipped = load_run(clean_df, config, engine=mock_engine)
        assert inserted == 2
        assert skipped == 1


class TestEmptyDataFrame:
    def test_empty_df_returns_zero_zero(self):
        config = _make_config()
        mock_engine = MagicMock()
        inserted, skipped = load_run(pd.DataFrame(), config, engine=mock_engine)
        assert inserted == 0
        assert skipped == 0
        mock_engine.begin.assert_not_called()


class TestBatching:
    def test_large_df_split_into_batches(self):
        config = _make_config(batch_size=2)
        clean_df = _make_clean_df(5)
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_conn.execute.return_value = mock_result
        mock_engine.begin.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.begin.return_value.__exit__ = MagicMock(return_value=False)

        load_run(clean_df, config, engine=mock_engine)
        # 5 rows / batch_size=2 → 3 batches (2+2+1)
        assert mock_conn.execute.call_count == 3


class TestColumnMapping:
    def test_all_csv_columns_have_db_mapping(self):
        expected = {
            "OrderID", "CustomerID", "ProductID", "ProductName", "Category",
            "Quantity", "UnitPrice", "TotalPrice", "OrderDate", "Region", "source_file"
        }
        assert set(COLUMN_MAP.keys()) == expected
