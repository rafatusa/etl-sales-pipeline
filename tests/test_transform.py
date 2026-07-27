"""Unit tests for the transform stage."""

import pandas as pd
import pytest

from etl.transform import run as transform_run


def _make_df(rows: list[dict]) -> pd.DataFrame:
    """Helper: create a DataFrame from a list of dicts."""
    return pd.DataFrame(rows)


BASE_ROW = {
    "OrderID": "ORD-001",
    "CustomerID": "CUST-101",
    "ProductID": "PROD-A1",
    "ProductName": "Wireless Mouse",
    "Category": "Electronics",
    "Quantity": "2",
    "UnitPrice": "29.99",
    "OrderDate": "2024-01-15",
    "Region": "North",
}


class TestTotalPriceCalculation:
    def test_total_price_equals_quantity_times_unit_price(self):
        df = _make_df([BASE_ROW])
        clean, rejected = transform_run(df, "test.csv")
        assert len(clean) == 1
        assert clean.iloc[0]["TotalPrice"] == pytest.approx(2 * 29.99)

    def test_total_price_zero_unit_price(self):
        row = {**BASE_ROW, "UnitPrice": "0.00"}
        df = _make_df([row])
        clean, _ = transform_run(df, "test.csv")
        assert clean.iloc[0]["TotalPrice"] == pytest.approx(0.0)

    def test_total_price_large_quantity(self):
        row = {**BASE_ROW, "Quantity": "100", "UnitPrice": "9.99"}
        df = _make_df([row])
        clean, _ = transform_run(df, "test.csv")
        assert clean.iloc[0]["TotalPrice"] == pytest.approx(100 * 9.99)


class TestDuplicateDetection:
    def test_duplicate_order_product_removed(self):
        dup_row = {**BASE_ROW}
        df = _make_df([BASE_ROW, dup_row])
        clean, rejected = transform_run(df, "test.csv")
        assert len(clean) == 1
        assert any("duplicate" in str(r) for r in rejected["rejection_reason"])

    def test_same_order_different_product_kept(self):
        row2 = {**BASE_ROW, "ProductID": "PROD-B2", "ProductName": "Office Chair"}
        df = _make_df([BASE_ROW, row2])
        clean, rejected = transform_run(df, "test.csv")
        assert len(clean) == 2
        assert len(rejected) == 0

    def test_three_duplicates_keeps_only_first(self):
        df = _make_df([BASE_ROW, BASE_ROW, BASE_ROW])
        clean, rejected = transform_run(df, "test.csv")
        assert len(clean) == 1
        assert len(rejected) == 2


class TestInvalidRecordRejection:
    def test_blank_order_id_rejected(self):
        row = {**BASE_ROW, "OrderID": ""}
        df = _make_df([row])
        clean, rejected = transform_run(df, "test.csv")
        assert len(clean) == 0
        assert "blank_orderid" in str(rejected.iloc[0]["rejection_reason"])

    def test_negative_quantity_rejected(self):
        row = {**BASE_ROW, "Quantity": "-1"}
        df = _make_df([row])
        clean, rejected = transform_run(df, "test.csv")
        assert len(clean) == 0
        assert "invalid_quantity" in str(rejected.iloc[0]["rejection_reason"])

    def test_zero_quantity_rejected(self):
        row = {**BASE_ROW, "Quantity": "0"}
        df = _make_df([row])
        clean, rejected = transform_run(df, "test.csv")
        assert len(clean) == 0

    def test_non_numeric_unit_price_rejected(self):
        row = {**BASE_ROW, "UnitPrice": "not-a-price"}
        df = _make_df([row])
        clean, rejected = transform_run(df, "test.csv")
        assert len(clean) == 0
        assert "invalid_unit_price" in str(rejected.iloc[0]["rejection_reason"])

    def test_negative_unit_price_rejected(self):
        row = {**BASE_ROW, "UnitPrice": "-5.00"}
        df = _make_df([row])
        clean, rejected = transform_run(df, "test.csv")
        assert len(clean) == 0

    def test_invalid_date_rejected(self):
        row = {**BASE_ROW, "OrderDate": "not-a-date"}
        df = _make_df([row])
        clean, rejected = transform_run(df, "test.csv")
        assert len(clean) == 0
        assert "invalid_date" in str(rejected.iloc[0]["rejection_reason"])

    def test_blank_customer_id_rejected(self):
        row = {**BASE_ROW, "CustomerID": ""}
        df = _make_df([row])
        clean, rejected = transform_run(df, "test.csv")
        assert len(clean) == 0


class TestSourceFileColumn:
    def test_source_file_added_to_clean_rows(self):
        df = _make_df([BASE_ROW])
        clean, _ = transform_run(df, "input/my-file.csv")
        assert "source_file" in clean.columns
        assert clean.iloc[0]["source_file"] == "input/my-file.csv"


class TestMixedData:
    def test_sample_csv_stats(self):
        """Matches the known composition of data/sample_sales.csv:
        50 rows total: 2 exact duplicates, 4 invalid rows = 44 clean rows."""
        import io
        import os
        csv_path = os.path.join(os.path.dirname(__file__), "..", "data", "sample_sales.csv")
        raw_df = pd.read_csv(csv_path, dtype=str)
        clean, rejected = transform_run(raw_df, "sample_sales.csv")
        assert len(clean) >= 40  # at least 40 clean rows
        assert len(rejected) >= 4  # at least 4 invalid/duplicate rows
        assert all(clean["TotalPrice"] >= 0)
