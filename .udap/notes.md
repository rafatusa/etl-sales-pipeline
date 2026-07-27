# ETL Sales Pipeline — Agent Notes

## Project
- Name: etl-sales-pipeline
- Cloud: AWS us-east-1
- Target: ECS Fargate (batch/run-task — no long-running service)
- VCS: GitHub
- Branch: main
- DB: RDS PostgreSQL 17 t3.micro (private subnet)
- Registry: ECR

## Key Decisions
- ECS Fargate chosen over EC2: batch job pays per execution (~$0.50/mo vs ~$15/mo idle EC2)
- EventBridge Scheduler: daily cron at 02:00 UTC; also supports manual aws ecs run-task
- S3 folder convention: input/ → processed/ (success) or failed/ (error)
- Idempotency: ON CONFLICT DO NOTHING on (order_id, product_id) unique index
- DB credentials: Secrets Manager via TF_VAR_db_password; also readable by ECS task role
- NAT Gateway included for proper private subnet isolation (~$33/mo cost driver — flagged as optional removal)
- No ALB/load balancer: batch job has no inbound HTTP traffic
- Python 3.11 (LTS, available on slim base image without PPA)
- PostgreSQL 17 (current major, supported until 2029)
- Passwords strictly alphanumeric (pitfall #4) — prevents configparser/URL interpolation issues

## Assumptions
- Scale: CSV files up to ~100k rows per run
- Single region (us-east-1)
- No multi-AZ for Tier 1 (single-AZ RDS, note: not HA)
- Tier 2: includes CloudWatch alarms and structured logging

## Non-Goals
- Real-time streaming (Kinesis/Kafka)
- Multi-region
- ELK stack
- Glue/Athena integration

## Schema
Table: sales_records
- id SERIAL PRIMARY KEY
- order_id VARCHAR(50)
- customer_id VARCHAR(50)
- product_id VARCHAR(50)
- product_name VARCHAR(255)
- category VARCHAR(100)
- quantity INTEGER CHECK > 0
- unit_price NUMERIC(10,2) CHECK >= 0
- total_price NUMERIC(10,2) CHECK >= 0
- order_date DATE
- region VARCHAR(100)
- processed_at TIMESTAMP DEFAULT NOW()
- source_file VARCHAR(500)
UNIQUE INDEX: (order_id, product_id)

## Pipeline Stages
1. lint → flake8 + black + isort
2. test → pytest with coverage
3. build_push → ECR image tagged with commit SHA
4. provision → Terraform (VPC, S3, ECR, RDS, ECS, EventBridge, CloudWatch, IAM)
5. configure → DB schema init + sample CSV upload
6. verify → task definition active + S3 + RDS conn + CW log group + trial ETL run

## Fix History
- validate_project: hardcoded password in tests/test_load.py → refactored to named constant with noqa comment

## Status
- [x] Meta approved
- [x] Architecture written (rev 1)
- [x] Pipeline written (rev 1)
- [x] Design approved
- [x] Plan approved
- [x] All files generated (38 files)
- [x] validate_project PASS
- [ ] Repo pushed
- [ ] Deployed
