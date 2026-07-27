"""Unit tests for the extract stage."""

import io
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from etl.extract import (
    REQUIRED_COLUMNS,
    download_csv,
    list_input_files,
    validate_columns,
)


class TestListInputFiles:
    def test_returns_csv_keys_sorted_by_date(self):
        s3_client = MagicMock()
        from datetime import datetime, timezone

        s3_client.list_objects_v2.return_value = {
            "Contents": [
                {"Key": "input/b.csv", "LastModified": datetime(2024, 1, 2, tzinfo=timezone.utc)},
                {"Key": "input/a.csv", "LastModified": datetime(2024, 1, 1, tzinfo=timezone.utc)},
                {"Key": "input/c.csv", "LastModified": datetime(2024, 1, 3, tzinfo=timezone.utc)},
            ]
        }
        result = list_input_files(s3_client, "my-bucket", "input/")
        assert result == ["input/a.csv", "input/b.csv", "input/c.csv"]

    def test_ignores_non_csv_files(self):
        s3_client = MagicMock()
        from datetime import datetime, timezone

        s3_client.list_objects_v2.return_value = {
            "Contents": [
                {"Key": "input/data.csv", "LastModified": datetime(2024, 1, 1, tzinfo=timezone.utc)},
                {"Key": "input/readme.txt", "LastModified": datetime(2024, 1, 1, tzinfo=timezone.utc)},
            ]
        }
        result = list_input_files(s3_client, "my-bucket", "input/")
        assert result == ["input/data.csv"]

    def test_empty_bucket_returns_empty_list(self):
        s3_client = MagicMock()
        s3_client.list_objects_v2.return_value = {"Contents": []}
        result = list_input_files(s3_client, "my-bucket", "input/")
        assert result == []

    def test_no_contents_key_returns_empty_list(self):
        s3_client = MagicMock()
        s3_client.list_objects_v2.return_value = {}
        result = list_input_files(s3_client, "my-bucket", "input/")
        assert result == []


class TestDownloadCsv:
    def _mock_s3(self, csv_content: str):
        s3 = MagicMock()
        s3.get_object.return_value = {
            "Body": MagicMock(read=MagicMock(return_value=csv_content.encode("utf-8")))
        }
        return s3

    def test_valid_csv_returns_dataframe(self):
        csv = "OrderID,CustomerID,ProductID,ProductName,Category,Quantity,UnitPrice,OrderDate,Region\n"
        csv += "ORD-001,CUST-101,PROD-A1,Mouse,Electronics,2,29.99,2024-01-15,North\n"
        s3 = self._mock_s3(csv)
        df = download_csv(s3, "bucket", "input/test.csv")
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 1

    def test_empty_file_raises(self):
        s3 = self._mock_s3("   ")
        with pytest.raises(ValueError, match="empty"):
            download_csv(s3, "bucket", "input/empty.csv")


class TestValidateColumns:
    def test_all_required_columns_present_passes(self):
        df = pd.DataFrame(columns=list(REQUIRED_COLUMNS))
        validate_columns(df, "test.csv")  # Should not raise

    def test_missing_column_raises(self):
        cols = list(REQUIRED_COLUMNS - {"UnitPrice"})
        df = pd.DataFrame(columns=cols)
        with pytest.raises(ValueError, match="UnitPrice"):
            validate_columns(df, "test.csv")

    def test_extra_columns_allowed(self):
        df = pd.DataFrame(columns=list(REQUIRED_COLUMNS) + ["ExtraColumn"])
        validate_columns(df, "test.csv")  # Should not raise
