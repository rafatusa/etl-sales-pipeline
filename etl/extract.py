"""
Extract stage — download the target CSV from S3 and return a raw DataFrame.

Responsibilities:
  - List files in the input/ prefix and pick the oldest unprocessed file
  - Download to an in-memory buffer (no temp files on disk)
  - Basic sanity checks: file exists, non-empty, has expected columns
  - Return raw DataFrame + source S3 key (passed to later stages for move)
"""

import io
from typing import Optional

import boto3
import pandas as pd

from etl.config import Config
from etl.logger import get_logger

logger = get_logger(__name__)

REQUIRED_COLUMNS = {
    "OrderID",
    "CustomerID",
    "ProductID",
    "ProductName",
    "Category",
    "Quantity",
    "UnitPrice",
    "OrderDate",
    "Region",
}


def list_input_files(s3_client, bucket: str, prefix: str) -> list[str]:
    """Return all CSV keys in the input prefix, sorted by LastModified (oldest first)."""
    response = s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix)
    objects = response.get("Contents", [])
    csv_objects = [obj for obj in objects if obj["Key"].endswith(".csv")]
    csv_objects.sort(key=lambda o: o["LastModified"])
    return [obj["Key"] for obj in csv_objects]


def download_csv(s3_client, bucket: str, key: str) -> pd.DataFrame:
    """Download a CSV from S3 and parse it into a DataFrame."""
    logger.info(
        "Downloading CSV from S3",
        extra={"stage": "extract", "file": f"s3://{bucket}/{key}"},
    )
    response = s3_client.get_object(Bucket=bucket, Key=key)
    content = response["Body"].read()

    if not content.strip():
        raise ValueError(f"S3 file is empty: s3://{bucket}/{key}")

    df = pd.read_csv(io.BytesIO(content), dtype=str)
    logger.info(
        f"Downloaded {len(df)} raw rows",
        extra={"stage": "extract", "file": key},
    )
    return df


def validate_columns(df: pd.DataFrame, source_key: str) -> None:
    """Raise if the CSV is missing any required columns."""
    present = set(df.columns)
    missing = REQUIRED_COLUMNS - present
    if missing:
        raise ValueError(
            f"CSV '{source_key}' is missing required columns: {sorted(missing)}"
        )


def run(config: Config, s3_key: Optional[str] = None) -> tuple[pd.DataFrame, str]:
    """
    Run the extract stage.

    Args:
        config: application configuration
        s3_key:  explicit S3 key to process; if None, picks the oldest file
                 in the input/ prefix.

    Returns:
        (raw_dataframe, s3_key_processed)
    """
    s3 = boto3.client("s3", region_name=config.aws_region)

    if s3_key is None:
        keys = list_input_files(s3, config.s3_bucket, config.s3_input_prefix)
        if not keys:
            raise FileNotFoundError(
                f"No CSV files found at s3://{config.s3_bucket}/{config.s3_input_prefix}"
            )
        s3_key = keys[0]
        logger.info(
            f"Auto-selected oldest input file: {s3_key}",
            extra={"stage": "extract"},
        )

    df = download_csv(s3, config.s3_bucket, s3_key)
    validate_columns(df, s3_key)

    logger.info(
        "Extract stage complete",
        extra={
            "stage": "extract",
            "event": "extract_complete",
            "file": s3_key,
            "rows": len(df),
        },
    )
    return df, s3_key
