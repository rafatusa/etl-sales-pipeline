variable "project_name" {
  type        = string
  description = "Project name used as prefix for all AWS resources"
}

variable "region" {
  type        = string
  description = "AWS region to deploy into"
  default     = "us-east-1"
}

variable "db_password" {
  type        = string
  description = "RDS master password (injected via TF_VAR_db_password secret)"
  sensitive   = true
}

variable "db_instance_class" {
  type        = string
  description = "RDS instance class"
  default     = "db.t3.micro"
}

variable "db_name" {
  type        = string
  description = "Name of the PostgreSQL database"
  default     = "salesdb"
}

variable "db_username" {
  type        = string
  description = "RDS master username"
  default     = "etladmin"
}

variable "ecs_cpu" {
  type        = number
  description = "ECS Fargate task CPU units (1024 = 1 vCPU)"
  default     = 1024
}

variable "ecs_memory" {
  type        = number
  description = "ECS Fargate task memory in MiB"
  default     = 2048
}

variable "image_tag" {
  type        = string
  description = "Docker image tag (commit SHA from CI)"
  default     = "latest"
}

variable "etl_schedule" {
  type        = string
  description = "EventBridge cron schedule expression (UTC)"
  default     = "cron(0 2 * * ? *)"
}

variable "log_retention_days" {
  type        = number
  description = "CloudWatch log group retention in days"
  default     = 30
}

variable "s3_input_prefix" {
  type        = string
  description = "S3 prefix for incoming CSV files"
  default     = "input/"
}
