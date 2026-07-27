"""
Data quality report — emitted as a structured JSON log entry after every ETL run.

The CloudWatch metric filter { $.event = "quality_report" } extracts:
  - $.records.successful_inserts  → RecordsProcessed metric
  - $.records.duplicates_removed  → DuplicatesRemoved metric
  - $.records.invalid_records     → InvalidRecords metric

The report is also returned as a dict for use in tests and the pipeline summary.
"""

import time
from dataclasses import asdict, dataclass, field
from typing import Optional

import pandas as pd

from etl.logger import get_logger

logger = get_logger(__name__)


@dataclass
class InvalidBreakdown:
    blank_ids: int = 0
    invalid_date: int = 0
    invalid_quantity: int = 0
    invalid_unit_price: int = 0
    other: int = 0


@dataclass
class QualityReport:
    source_file: str
    total_input: int
    duplicates_removed: int
    invalid_records: int
    invalid_breakdown: InvalidBreakdown
    successful_inserts: int
    skipped_inserts: int  # already existed in DB (idempotent re-runs)
    failed_records: int
    execution_time_seconds: float
    status: str  # "success" | "partial" | "failed"
    error_message: Optional[str] = None


def build(
    source_file: str,
    total_input: int,
    rejected_df: pd.DataFrame,
    duplicates_removed: int,
    successful_inserts: int,
    skipped_inserts: int,
    failed_records: int,
    start_time: float,
    status: str = "success",
    error_message: Optional[str] = None,
) -> QualityReport:
    """Construct a QualityReport from pipeline stage outputs."""
    elapsed = round(time.monotonic() - start_time, 2)

    # Categorize rejection reasons
    breakdown = InvalidBreakdown()
    if not rejected_df.empty and "rejection_reason" in rejected_df.columns:
        for reason in rejected_df["rejection_reason"].dropna():
            reason_str = str(reason)
            if "blank_" in reason_str:
                breakdown.blank_ids += 1
            elif "invalid_date" in reason_str:
                breakdown.invalid_date += 1
            elif "invalid_quantity" in reason_str:
                breakdown.invalid_quantity += 1
            elif "invalid_unit_price" in reason_str:
                breakdown.invalid_unit_price += 1
            elif "duplicate" not in reason_str:
                breakdown.other += 1

    # Don't count duplicates in invalid_records
    pure_invalid = len(rejected_df[
        ~rejected_df.get("rejection_reason", pd.Series(dtype=str)).str.contains(
            "duplicate", na=False
        )
    ]) if not rejected_df.empty else 0

    return QualityReport(
        source_file=source_file,
        total_input=total_input,
        duplicates_removed=duplicates_removed,
        invalid_records=pure_invalid,
        invalid_breakdown=breakdown,
        successful_inserts=successful_inserts,
        skipped_inserts=skipped_inserts,
        failed_records=failed_records,
        execution_time_seconds=elapsed,
        status=status,
        error_message=error_message,
    )


def emit(report: QualityReport) -> dict:
    """Log the quality report as a structured JSON event and return it as a dict."""
    report_dict = asdict(report)

    logger.info(
        "ETL data quality report",
        extra={
            "event": "quality_report",
            "file": report.source_file,
            "records": {
                "total_input": report.total_input,
                "duplicates_removed": report.duplicates_removed,
                "invalid_records": report.invalid_records,
                "successful_inserts": report.successful_inserts,
                "skipped_inserts": report.skipped_inserts,
                "failed_records": report.failed_records,
            },
            "duration_seconds": report.execution_time_seconds,
            "status": report.status,
        },
    )

    if report.status != "success":
        logger.error(
            f"Pipeline completed with status: {report.status}",
            extra={
                "event": "pipeline_failed",
                "error": report.error_message,
                "status": report.status,
            },
        )

    return report_dict
