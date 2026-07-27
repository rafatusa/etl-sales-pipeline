output "rds_endpoint" {
  description = "RDS PostgreSQL hostname (without port)"
  value       = aws_db_instance.postgres.address
}

output "rds_port" {
  description = "RDS PostgreSQL port"
  value       = aws_db_instance.postgres.port
}

output "s3_bucket_name" {
  description = "S3 landing bucket name"
  value       = aws_s3_bucket.landing.bucket
}

output "ecr_repository_url" {
  description = "ECR repository URL for the ETL image"
  value       = aws_ecr_repository.etl.repository_url
}

output "ecs_cluster_name" {
  description = "ECS cluster name"
  value       = aws_ecs_cluster.main.name
}

output "ecs_task_definition_arn" {
  description = "ECS task definition ARN"
  value       = aws_ecs_task_definition.etl.arn
}

output "ecs_task_sg_id" {
  description = "ECS task security group ID"
  value       = aws_security_group.ecs_task.id
}

output "private_subnet_id" {
  description = "First private subnet ID (used for ECS task runs)"
  value       = aws_subnet.private[0].id
}

output "eventbridge_schedule_arn" {
  description = "EventBridge Scheduler schedule ARN"
  value       = aws_scheduler_schedule.etl_daily.arn
}

output "cloudwatch_log_group" {
  description = "CloudWatch log group name for ETL container logs"
  value       = aws_cloudwatch_log_group.etl.name
}

output "secrets_manager_arn" {
  description = "Secrets Manager ARN for DB credentials"
  value       = aws_secretsmanager_secret.db_credentials.arn
}

output "vpc_id" {
  description = "VPC ID"
  value       = aws_vpc.main.id
}
