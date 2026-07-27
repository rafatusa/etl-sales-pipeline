###############################################################################
# CloudWatch — log group, metric filters, alarms
###############################################################################

resource "aws_cloudwatch_log_group" "etl" {
  name              = "/ecs/${var.project_name}"
  retention_in_days = var.log_retention_days

  tags = { Name = "${var.project_name}-log-group" }
}

###############################################################################
# Metric Filters — extract business metrics from structured JSON logs
###############################################################################

resource "aws_cloudwatch_log_metric_filter" "etl_errors" {
  name           = "${var.project_name}-etl-errors"
  log_group_name = aws_cloudwatch_log_group.etl.name
  pattern        = "{ $.level = \"ERROR\" }"

  metric_transformation {
    name          = "ETLErrors"
    namespace     = "${var.project_name}/ETL"
    value         = "1"
    default_value = "0"
    unit          = "Count"
  }
}

resource "aws_cloudwatch_log_metric_filter" "etl_records_processed" {
  name           = "${var.project_name}-records-processed"
  log_group_name = aws_cloudwatch_log_group.etl.name
  pattern        = "{ $.event = \"quality_report\" }"

  metric_transformation {
    name          = "RecordsProcessed"
    namespace     = "${var.project_name}/ETL"
    value         = "$.records.successful_inserts"
    default_value = "0"
    unit          = "Count"
  }
}

resource "aws_cloudwatch_log_metric_filter" "etl_duplicates_removed" {
  name           = "${var.project_name}-duplicates-removed"
  log_group_name = aws_cloudwatch_log_group.etl.name
  pattern        = "{ $.event = \"quality_report\" }"

  metric_transformation {
    name          = "DuplicatesRemoved"
    namespace     = "${var.project_name}/ETL"
    value         = "$.records.duplicates_removed"
    default_value = "0"
    unit          = "Count"
  }
}

resource "aws_cloudwatch_log_metric_filter" "etl_invalid_records" {
  name           = "${var.project_name}-invalid-records"
  log_group_name = aws_cloudwatch_log_group.etl.name
  pattern        = "{ $.event = \"quality_report\" }"

  metric_transformation {
    name          = "InvalidRecords"
    namespace     = "${var.project_name}/ETL"
    value         = "$.records.invalid_records"
    default_value = "0"
    unit          = "Count"
  }
}

resource "aws_cloudwatch_log_metric_filter" "etl_pipeline_failure" {
  name           = "${var.project_name}-pipeline-failure"
  log_group_name = aws_cloudwatch_log_group.etl.name
  pattern        = "{ $.event = \"pipeline_failed\" }"

  metric_transformation {
    name          = "PipelineFailures"
    namespace     = "${var.project_name}/ETL"
    value         = "1"
    default_value = "0"
    unit          = "Count"
  }
}

###############################################################################
# CloudWatch Alarms
###############################################################################

resource "aws_cloudwatch_metric_alarm" "etl_errors" {
  alarm_name          = "${var.project_name}-etl-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ETLErrors"
  namespace           = "${var.project_name}/ETL"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  alarm_description   = "ETL pipeline produced ERROR level log entries"
  treat_missing_data  = "notBreaching"

  tags = { Name = "${var.project_name}-etl-errors-alarm" }
}

resource "aws_cloudwatch_metric_alarm" "etl_pipeline_failure" {
  alarm_name          = "${var.project_name}-pipeline-failure"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "PipelineFailures"
  namespace           = "${var.project_name}/ETL"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  alarm_description   = "ETL pipeline completed with failure status"
  treat_missing_data  = "notBreaching"

  tags = { Name = "${var.project_name}-pipeline-failure-alarm" }
}

resource "aws_cloudwatch_metric_alarm" "rds_cpu" {
  alarm_name          = "${var.project_name}-rds-cpu"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "CPUUtilization"
  namespace           = "AWS/RDS"
  period              = 300
  statistic           = "Average"
  threshold           = 80
  alarm_description   = "RDS CPU utilization exceeded 80%"
  treat_missing_data  = "notBreaching"

  dimensions = {
    DBInstanceIdentifier = aws_db_instance.postgres.identifier
  }

  tags = { Name = "${var.project_name}-rds-cpu-alarm" }
}

resource "aws_cloudwatch_metric_alarm" "rds_storage" {
  alarm_name          = "${var.project_name}-rds-storage"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = 1
  metric_name         = "FreeStorageSpace"
  namespace           = "AWS/RDS"
  period              = 300
  statistic           = "Average"
  threshold           = 2000000000  # 2 GB in bytes
  alarm_description   = "RDS free storage below 2 GB"
  treat_missing_data  = "notBreaching"

  dimensions = {
    DBInstanceIdentifier = aws_db_instance.postgres.identifier
  }

  tags = { Name = "${var.project_name}-rds-storage-alarm" }
}
