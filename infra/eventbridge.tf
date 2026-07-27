###############################################################################
# EventBridge Scheduler — daily cron + manual trigger support
###############################################################################

resource "aws_scheduler_schedule" "etl_daily" {
  name                         = "${var.project_name}-daily-etl"
  description                  = "Trigger ETL Fargate task daily at 02:00 UTC"
  schedule_expression          = var.etl_schedule
  schedule_expression_timezone = "UTC"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_ecs_cluster.main.arn
    role_arn = aws_iam_role.eventbridge_scheduler.arn

    ecs_parameters {
      task_definition_arn = aws_ecs_task_definition.etl.arn
      task_count          = 1
      launch_type         = "FARGATE"

      network_configuration {
        assign_public_ip = false
        security_groups  = [aws_security_group.ecs_task.id]
        subnets          = [aws_subnet.private[0].id]
      }
    }

    retry_policy {
      maximum_retry_attempts       = 2
      maximum_event_age_in_seconds = 3600
    }
  }
}
