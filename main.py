#!/usr/bin/env python3
"""
ETL Sales Pipeline — container entrypoint.

Loads configuration from environment variables, configures structured logging,
and runs the full Extract → Transform → Load pipeline.

Exits with code 0 on success, 1 on failure.
"""

import os
import sys

from etl.config import Config
from etl.logger import configure_root_logger, get_logger
from etl import pipeline


def main() -> int:
    # Bootstrap logging first (before importing anything that logs)
    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
    configure_root_logger(log_level)
    logger = get_logger(__name__)

    logger.info("ETL Sales Pipeline starting up", extra={"stage": "main"})

    try:
        config = Config.from_env()
    except EnvironmentError as exc:
        logger.error(str(exc), extra={"stage": "main"})
        return 1

    # Optional: allow overriding the S3 key via environment (useful for manual runs)
    s3_key = os.environ.get("S3_KEY") or None

    exit_code = pipeline.run(config, s3_key=s3_key)

    logger.info(
        f"ETL Sales Pipeline finished with exit code {exit_code}",
        extra={"stage": "main", "exit_code": exit_code},
    )
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
