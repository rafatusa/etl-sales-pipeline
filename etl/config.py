"""
Configuration loader — reads all settings from environment variables.
No hardcoded values; raises clearly if required vars are absent.
"""

import os
from dataclasses import dataclass, field


@dataclass
class Config:
    # AWS
    aws_region: str = field(
        default_factory=lambda: os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
    )

    # S3
    s3_bucket: str = field(default_factory=lambda: os.environ["S3_BUCKET"])
    s3_input_prefix: str = field(
        default_factory=lambda: os.environ.get("S3_INPUT_PREFIX", "input/")
    )
    s3_processed_prefix: str = field(
        default_factory=lambda: os.environ.get("S3_PROCESSED_PREFIX", "processed/")
    )
    s3_failed_prefix: str = field(
        default_factory=lambda: os.environ.get("S3_FAILED_PREFIX", "failed/")
    )

    # Database
    db_host: str = field(default_factory=lambda: os.environ["DB_HOST"])
    db_port: int = field(
        default_factory=lambda: int(os.environ.get("DB_PORT", "5432"))
    )
    db_name: str = field(
        default_factory=lambda: os.environ.get("DB_NAME", "salesdb")
    )
    db_user: str = field(default_factory=lambda: os.environ["DB_USER"])
    db_password: str = field(default_factory=lambda: os.environ["DB_PASSWORD"])
    db_ssl_mode: str = field(
        default_factory=lambda: os.environ.get("DB_SSL_MODE", "require")
    )

    # ETL behaviour
    batch_size: int = field(
        default_factory=lambda: int(os.environ.get("BATCH_SIZE", "500"))
    )
    max_retries: int = field(
        default_factory=lambda: int(os.environ.get("MAX_RETRIES", "3"))
    )
    retry_delay_seconds: int = field(
        default_factory=lambda: int(os.environ.get("RETRY_DELAY_SECONDS", "5"))
    )

    # Logging
    log_level: str = field(
        default_factory=lambda: os.environ.get("LOG_LEVEL", "INFO").upper()
    )
    environment: str = field(
        default_factory=lambda: os.environ.get("ENVIRONMENT", "development")
    )

    @property
    def db_url(self) -> str:
        """SQLAlchemy connection URL (sslmode appended as query parameter)."""
        return (
            f"postgresql+psycopg2://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
            f"?sslmode={self.db_ssl_mode}"
        )

    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment, raising on missing required values."""
        required = ["S3_BUCKET", "DB_HOST", "DB_USER", "DB_PASSWORD"]
        missing = [k for k in required if not os.environ.get(k)]
        if missing:
            raise EnvironmentError(
                f"Missing required environment variables: {', '.join(missing)}"
            )
        return cls()
