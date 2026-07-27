###############################################################################
# ECS Fargate — cluster + task definition (run-task only, no long-running svc)
###############################################################################

resource "aws_ecs_cluster" "main" {
  name = "${var.project_name}-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = { Name = "${var.project_name}-cluster" }
}

resource "aws_ecs_cluster_capacity_providers" "main" {
  cluster_name       = aws_ecs_cluster.main.name
  capacity_providers = ["FARGATE", "FARGATE_SPOT"]

  default_capacity_provider_strategy {
    capacity_provider = "FARGATE"
    weight            = 1
    base              = 1
  }
}

resource "aws_ecs_task_definition" "etl" {
  family                   = "${var.project_name}-etl"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.ecs_cpu
  memory                   = var.ecs_memory
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([{
    name      = "etl"
    image     = "${aws_ecr_repository.etl.repository_url}:${var.image_tag}"
    essential = true

    environment = [
      { name = "AWS_DEFAULT_REGION", value = var.region },
      { name = "S3_BUCKET",          value = aws_s3_bucket.landing.bucket },
      { name = "S3_INPUT_PREFIX",    value = var.s3_input_prefix },
      { name = "DB_HOST",            value = aws_db_instance.postgres.address },
      { name = "DB_PORT",            value = "5432" },
      { name = "DB_NAME",            value = var.db_name },
      { name = "DB_USER",            value = var.db_username },
      { name = "LOG_LEVEL",          value = "INFO" },
      { name = "ENVIRONMENT",        value = "production" }
    ]

    secrets = [{
      name      = "DB_PASSWORD"
      valueFrom = "${aws_secretsmanager_secret.db_credentials.arn}:password::"
    }]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.etl.name
        "awslogs-region"        = var.region
        "awslogs-stream-prefix" = "etl"
      }
    }

    healthCheck = null  # Batch task — no long-running process to health-check
  }])

  tags = { Name = "${var.project_name}-etl-task" }
}
