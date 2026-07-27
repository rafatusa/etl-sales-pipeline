###############################################################################
# IAM — ECS task execution role + task role (least privilege)
###############################################################################

# Task Execution Role — allows ECS agent to pull image + push logs
resource "aws_iam_role" "ecs_task_execution" {
  name = "${var.project_name}-ecs-exec-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_task_execution" {
  role       = aws_iam_role.ecs_task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Task Role — application-level permissions (S3 + CloudWatch + Secrets Manager)
resource "aws_iam_role" "ecs_task" {
  name = "${var.project_name}-ecs-task-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_policy" "ecs_task" {
  name        = "${var.project_name}-ecs-task-policy"
  description = "ETL task: S3 read/write (landing bucket), CloudWatch logs, Secrets Manager read"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "S3LandingBucket"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket",
          "s3:HeadObject"
        ]
        Resource = [
          aws_s3_bucket.landing.arn,
          "${aws_s3_bucket.landing.arn}/*"
        ]
      },
      {
        Sid    = "CloudWatchLogs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents",
          "logs:DescribeLogStreams"
        ]
        Resource = "${aws_cloudwatch_log_group.etl.arn}:*"
      },
      {
        Sid    = "SecretsManagerRead"
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue",
          "secretsmanager:DescribeSecret"
        ]
        Resource = aws_secretsmanager_secret.db_credentials.arn
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_task" {
  role       = aws_iam_role.ecs_task.name
  policy_arn = aws_iam_policy.ecs_task.arn
}

###############################################################################
# Secrets Manager — DB credentials
###############################################################################

resource "aws_secretsmanager_secret" "db_credentials" {
  name                    = "${var.project_name}/db-credentials"
  description             = "RDS PostgreSQL credentials for ETL pipeline"
  recovery_window_in_days = 7

  tags = { Name = "${var.project_name}-db-credentials" }
}

resource "aws_secretsmanager_secret_version" "db_credentials" {
  secret_id = aws_secretsmanager_secret.db_credentials.id
  secret_string = jsonencode({
    host     = aws_db_instance.postgres.address
    port     = 5432
    dbname   = var.db_name
    username = var.db_username
    password = var.db_password
  })
}

###############################################################################
# EventBridge Scheduler execution role
###############################################################################

resource "aws_iam_role" "eventbridge_scheduler" {
  name = "${var.project_name}-eventbridge-scheduler-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "scheduler.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_policy" "eventbridge_scheduler" {
  name        = "${var.project_name}-eventbridge-scheduler-policy"
  description = "Allow EventBridge Scheduler to run ECS tasks"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ECSRunTask"
        Effect = "Allow"
        Action = ["ecs:RunTask"]
        Resource = [
          "arn:aws:ecs:${var.region}:*:task-definition/${var.project_name}-etl:*"
        ]
      },
      {
        Sid    = "PassRole"
        Effect = "Allow"
        Action = ["iam:PassRole"]
        Resource = [
          aws_iam_role.ecs_task_execution.arn,
          aws_iam_role.ecs_task.arn
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "eventbridge_scheduler" {
  role       = aws_iam_role.eventbridge_scheduler.name
  policy_arn = aws_iam_policy.eventbridge_scheduler.arn
}
