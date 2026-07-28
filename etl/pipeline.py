"""
Pipeline orchestrator — runs Extract -> Transform -> Load in sequence.

Responsibilities:
  - Coordinate the three ETL stages
  - Move the source CSV to processed/ (success) or failed/ (error) in S3
  - Emit the data quality report
  - Return exit code 0 (success) or 1 (failure) to the container entrypoint
  - Implement retry logic with exponential backoff for transient failures
"""

import time
from typing import Optional

import boto3
import pandas as _pd

from etl import extract, load, transform
from etl.config import Config
from etl.logger import get_logger
from etl.quality_report import build as build_report
from etl.quality_report import emit as emit_report

logger = get_logger(__name__)


def _move_s3_object(
    s3_client,
    bucket: str,
    source_key: str,
    dest_prefix: str,
    filename: str,
) -> None:
    """Copy source_key to dest_prefix/filename, then delete the original."""
    dest_key = f"{dest_prefix.rstrip('/')}/{filename}"
    copy_source = {"Bucket": bucket, "Key": source_key}
    s3_client.copy_object(Bucket=bucket, CopySource=copy_source, Key=dest_key)
    s3_client.delete_object(Bucket=bucket, Key=source_key)
    logger.info(
        f"Moved s3://{bucket}/{source_key} -> s3://{bucket}/{dest_key}",
        extra={"stage": "pipeline"},
    )


def _run_with_retry(fn, config: Config, stage_name: str, *args, **kwargs):
    """Call fn(*args, **kwargs) with up to config.max_retries attempts."""
    last_exc = None
    for attempt in range(1, config.max_retries + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            last_exc = exc
            if attempt < config.max_retries:
                delay = config.retry_delay_seconds * (2 ** (attempt - 1))
                logger.warning(
                    f"{stage_name} attempt {attempt} failed; retrying in {delay}s",
                    extra={
                        "stage": stage_name,
                        "attempt": attempt,
                        "error": str(exc),
                    },
                )
                time.sleep(delay)
            else:
                logger.error(
                    f"{stage_name} failed after {config.max_retries} attempts",
                    extra={
                        "stage": stage_name,
                        "attempts": config.max_retries,
                        "error": str(exc),
                    },
                )
    raise last_exc  # type: ignore[misc]


def run(config: Config, s3_key: Optional[str] = None) -> int:
    """
    Execute the full ETL pipeline.

    Args:
        config: application configuration
        s3_key:  explicit S3 key to process (None = auto-select oldest input)

    Returns:
        0 on success, 1 on failure
    """
    pipeline_start = time.monotonic()
    s3 = boto3.client("s3", region_name=config.aws_region)
    source_key: Optional[str] = None
    rejected_df = None

    logger.info(
        "ETL pipeline starting",
        extra={"stage": "pipeline", "event": "pipeline_start"},
    )

    try:
        # -- Extract ----------------------------------------------------------
        raw_df, source_key = _run_with_retry(
            extract.run, config, "extract", config, s3_key
        )
        filename = source_key.split("/")[-1]
        total_input = len(raw_df)

        # -- Transform --------------------------------------------------------
        clean_df, rejected_df = _run_with_retry(
            transform.run, config, "transform", raw_df, source_key
        )
        duplicates_removed = sum(
            1
            for r in (
                rejected_df.get("rejection_reason", [])
                if rejected_df is not None
                else []
            )
            if "duplicate" in str(r)
        )

        # -- Load -------------------------------------------------------------
        successful_inserts, skipped_inserts = _run_with_retry(
            load.run, config, "load", clean_df, config
        )

        # -- Move CSV to processed/ ------------------------------------------
        _move_s3_object(
            s3, config.s3_bucket, source_key, config.s3_processed_prefix, filename
        )

        # -- Quality Report ---------------------------------------------------
        report = build_report(
            source_file=source_key,
            total_input=total_input,
            rejected_df=(
                rejected_df if rejected_df is not None else _pd.DataFrame()
            ),
            duplicates_removed=duplicates_removed,
            successful_inserts=successful_inserts,
            skipped_inserts=skipped_inserts,
            failed_records=0,
            start_time=pipeline_start,
            status="success",
        )
        emit_report(report)

        logger.info(
            "ETL pipeline completed successfully",
            extra={
                "stage": "pipeline",
                "event": "pipeline_complete",
                "status": "success",
            },
        )
        return 0

    except FileNotFoundError as exc:
        logger.warning(
            f"No input files found: {exc}",
            extra={"stage": "pipeline", "event": "no_input_files"},
        )
        # Not a failure — no files to process is a valid state
        return 0

    except Exception as exc:
        logger.error(
            f"Pipeline failed: {exc}",
            extra={"stage": "pipeline", "event": "pipeline_error", "error": str(exc)},
            exc_info=True,
        )

        # Move CSV to failed/ so it can be inspected
        if source_key:
            try:
                filename = source_key.split("/")[-1]
                _move_s3_object(
                    s3,
                    config.s3_bucket,
                    source_key,
                    config.s3_failed_prefix,
                    filename,
                )
            except Exception as move_exc:
                logger.error(
                    f"Failed to move CSV to failed/ prefix: {move_exc}",
                    extra={"stage": "pipeline"},
                )

        # Emit failure quality report
        report = build_report(
            source_file=source_key or "unknown",
            total_input=0,
            rejected_df=rejected_df if rejected_df is not None else _pd.DataFrame(),
            duplicates_removed=0,
            successful_inserts=0,
            skipped_inserts=0,
            failed_records=0,
            start_time=pipeline_start,
            status="failed",
            error_message=str(exc),
        )
        emit_report(report)
        return 1
