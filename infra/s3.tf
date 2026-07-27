###############################################################################
# S3 Landing Bucket — input / processed / failed prefixes
###############################################################################

resource "random_id" "bucket_suffix" {
  byte_length = 4
  keepers = {
    project = var.project_name
  }
}

resource "aws_s3_bucket" "landing" {
  bucket        = "${var.project_name}-landing-${random_id.bucket_suffix.hex}"
  force_destroy = false

  tags = { Name = "${var.project_name}-landing" }
}

resource "aws_s3_bucket_versioning" "landing" {
  bucket = aws_s3_bucket.landing.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "landing" {
  bucket = aws_s3_bucket.landing.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "landing" {
  bucket                  = aws_s3_bucket.landing.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "landing" {
  bucket = aws_s3_bucket.landing.id

  # Transition processed files to IA after 30 days, expire after 90
  rule {
    id     = "processed-lifecycle"
    status = "Enabled"
    filter {
      prefix = "processed/"
    }
    transition {
      days          = 30
      storage_class = "STANDARD_IA"
    }
    expiration {
      days = 90
    }
  }

  # Expire failed files after 30 days
  rule {
    id     = "failed-lifecycle"
    status = "Enabled"
    filter {
      prefix = "failed/"
    }
    expiration {
      days = 30
    }
  }

  # Keep input/ files for 7 days (should be moved on processing)
  rule {
    id     = "input-lifecycle"
    status = "Enabled"
    filter {
      prefix = "input/"
    }
    expiration {
      days = 7
    }
  }
}
