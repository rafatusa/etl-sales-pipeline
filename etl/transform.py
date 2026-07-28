"""
Transform stage — clean, validate, and enrich the raw DataFrame.

Rules applied in order:
  1. Strip leading/trailing whitespace from all string columns
  2. Parse and validate OrderDate as a date (YYYY-MM-DD)
  3. Cast Quantity to int — reject rows where it is not a positive integer
  4. Cast UnitPrice to float — reject rows where it is not a non-negative number
  5. Compute TotalPrice = Quantity x UnitPrice
  6. Reject rows where OrderID or CustomerID or ProductID is blank
  7. Deduplicate on (OrderID, ProductID) — keep first occurrence, tag rest as duplicates

Returns:
  clean_df    — rows that passed all checks, with TotalPrice column added
  rejected_df — rows that failed, with a 'rejection_reason' column
"""

from typing import Optional

import pandas as pd

from etl.logger import get_logger

logger = get_logger(__name__)


def _strip_strings(df: pd.DataFrame) -> pd.DataFrame:
    str_cols = df.select_dtypes(include="object").columns
    df[str_cols] = df[str_cols].apply(lambda col: col.str.strip())
    return df


def _validate_dates(
    df: pd.DataFrame,
    reject_mask: pd.Series,
    reasons: list,
) -> pd.Series:
    invalid = pd.to_datetime(
        df["OrderDate"], format="%Y-%m-%d", errors="coerce"
    ).isna()
    for i in df[invalid & ~reject_mask].index:
        reasons[i] = f"invalid_date:{df.at[i, 'OrderDate']}"
    return reject_mask | invalid


def _validate_quantity(
    df: pd.DataFrame,
    reject_mask: pd.Series,
    reasons: list,
) -> tuple[pd.Series, pd.Series]:
    numeric = pd.to_numeric(df["Quantity"], errors="coerce")
    invalid = numeric.isna() | (numeric <= 0) | (
        numeric != numeric.astype("Int64", errors="ignore")
    )
    for i in df[invalid & ~reject_mask].index:
        reasons[i] = f"invalid_quantity:{df.at[i, 'Quantity']}"
    return reject_mask | invalid, numeric


def _validate_unit_price(
    df: pd.DataFrame,
    reject_mask: pd.Series,
    reasons: list,
) -> tuple[pd.Series, pd.Series]:
    numeric = pd.to_numeric(df["UnitPrice"], errors="coerce")
    invalid = numeric.isna() | (numeric < 0)
    for i in df[invalid & ~reject_mask].index:
        reasons[i] = f"invalid_unit_price:{df.at[i, 'UnitPrice']}"
    return reject_mask | invalid, numeric


def _validate_required_ids(
    df: pd.DataFrame,
    reject_mask: pd.Series,
    reasons: list,
) -> pd.Series:
    for col in ("OrderID", "CustomerID", "ProductID"):
        blank = df[col].isna() | (df[col].str.strip() == "")
        for i in df[blank & ~reject_mask].index:
            reasons[i] = f"blank_{col.lower()}"
        reject_mask = reject_mask | blank
    return reject_mask


def run(raw_df: pd.DataFrame, source_file: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Run all transformation and validation rules.

    Returns:
        (clean_df, rejected_df) — clean has TotalPrice; rejected has rejection_reason.
    """
    logger.info(
        f"Starting transform on {len(raw_df)} rows",
        extra={"stage": "transform", "file": source_file},
    )

    df = raw_df.copy()
    df = _strip_strings(df)

    reject_mask = pd.Series(False, index=df.index)
    reasons: list[Optional[str]] = [None] * len(df)

    # Validate IDs
    reject_mask = _validate_required_ids(df, reject_mask, reasons)

    # Validate and cast dates
    reject_mask = _validate_dates(df, reject_mask, reasons)

    # Validate and cast Quantity
    reject_mask, quantity_numeric = _validate_quantity(df, reject_mask, reasons)

    # Validate and cast UnitPrice
    reject_mask, unit_price_numeric = _validate_unit_price(df, reject_mask, reasons)

    # Apply parsed types to the clean portion
    df["Quantity"] = quantity_numeric
    df["UnitPrice"] = unit_price_numeric
    df["OrderDate"] = pd.to_datetime(
        df["OrderDate"], format="%Y-%m-%d", errors="coerce"
    ).dt.date

    # Compute TotalPrice for valid rows before dedup
    df["TotalPrice"] = df["Quantity"] * df["UnitPrice"]

    # Separate invalid rows
    invalid_df = df[reject_mask].copy()
    invalid_df["rejection_reason"] = [reasons[i] for i in invalid_df.index]
    valid_df = df[~reject_mask].copy()

    # Deduplicate on (OrderID, ProductID) — keep first occurrence
    before_dedup = len(valid_df)
    dup_mask = valid_df.duplicated(subset=["OrderID", "ProductID"], keep="first")
    dups_df = valid_df[dup_mask].copy()
    dups_df["rejection_reason"] = "duplicate_order_product"
    valid_df = valid_df[~dup_mask].copy()
    after_dedup = len(valid_df)

    duplicates_removed = before_dedup - after_dedup
    invalid_count = len(invalid_df)

    # Combine all rejected rows
    rejected_df = pd.concat([invalid_df, dups_df], ignore_index=True)

    # Add source file column to clean rows
    valid_df["source_file"] = source_file

    # Final column selection and type alignment
    valid_df["Quantity"] = valid_df["Quantity"].astype(int)
    valid_df["UnitPrice"] = valid_df["UnitPrice"].astype(float)
    valid_df["TotalPrice"] = valid_df["TotalPrice"].astype(float)

    logger.info(
        "Transform stage complete",
        extra={
            "stage": "transform",
            "event": "transform_complete",
            "file": source_file,
            "total_input": len(raw_df),
            "valid_rows": len(valid_df),
            "invalid_rows": invalid_count,
            "duplicates_removed": duplicates_removed,
        },
    )

    return valid_df, rejected_df
