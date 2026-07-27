# ETL Sales Pipeline

A production-ready batch ETL pipeline that extracts customer sales data from S3 CSV files,
cleans and validates the data, computes `TotalPrice = Quantity × UnitPrice`, and loads the
results into PostgreSQL. Runs as an ECS Fargate task on a daily EventBridge schedule with
structured CloudWatch logging and automated data quality reporting.

---

## Architecture

```
Developer / CI
    │  docker push image → ECR
    │  upload CSV        → S3 (input/)
    │
EventBridge Scheduler ──── cron(0 2 * * ? *) ───► ECS Fargate Task (ETL Job)
                                                        │
                                         ┌──────────────┼──────────────────┐
                                         ▼              ▼                  ▼
                                   S3 Landing         RDS             CloudWatch
                                  input/  →         PostgreSQL        Logs + Alarms
                                  processed/         sales_records
                                  failed/
```

**AWS services and why each was chosen:**

| Service | Reason |
|---|---|
| **ECS Fargate** | Serverless container runtime — pay per execution (~$0.50/mo vs ~$15/mo idle EC2) |
| **ECR** | Private registry with native ECS integration and image scan on push |
| **S3** | Durable CSV landing zone with input/processed/failed folder lifecycle |
| **RDS PostgreSQL 17** | Managed DB — automated backups, encryption, minor-version patches |
| **EventBridge Scheduler** | Fully managed cron — no daemon, no EC2, 2-retry policy built in |
| **CloudWatch Logs + Alarms** | Zero-config structured logging from Fargate; metric filters extract ETL KPIs |
| **Secrets Manager** | DB credentials stored and rotated securely, referenced at task runtime |
| **VPC (private subnets)** | RDS never exposed publicly; ECS tasks egress via NAT Gateway |
| **IAM Task Role** | Least-privilege: S3 read/write + CloudWatch + Secrets Manager only |

**Estimated monthly cost (us-east-1):**

| Component | ~Cost |
|---|---|
| ECS Fargate (5 min/day) | $0.50 |
| ECR (1 GB image) | $0.10 |
| S3 | $0.05 |
| RDS t3.micro, single-AZ | $15.00 |
| CloudWatch Logs (5 GB) | $2.50 |
| NAT Gateway | $33.00 |
| **Total** | **~$51/mo** |

> 💡 **Cost tip:** Replace NAT Gateway with VPC endpoints for S3, ECR, and CloudWatch to save ~$33/mo.

---

## ETL Pipeline Stages

```
Extract → Transform → Load
```

### 1. Extract (`etl/extract.py`)
- Lists CSV files in `s3://<bucket>/input/`, picks the oldest
- Downloads to memory (no temp files)
- Validates presence of all required columns

### 2. Transform (`etl/transform.py`)
- Strips whitespace from all string columns
- Validates `OrderDate` format (YYYY-MM-DD)
- Validates `Quantity` > 0 (integer)
- Validates `UnitPrice` ≥ 0 (float)
- Rejects rows with blank `OrderID`, `CustomerID`, or `ProductID`
- Computes `TotalPrice = Quantity × UnitPrice`
- Deduplicates on `(OrderID, ProductID)` — keeps first occurrence

### 3. Load (`etl/load.py`)
- Upserts via `INSERT ... ON CONFLICT (order_id, product_id) DO NOTHING`
- Batch inserts of 500 rows (configurable)
- Returns `(inserted, skipped)` counts — re-processing the same file produces zero duplicates

### Data Quality Report
After every run a structured JSON log event is emitted with:
```json
{
  "event": "quality_report",
  "records": {
    "total_input": 50,
    "duplicates_removed": 2,
    "invalid_records": 3,
    "successful_inserts": 45,
    "skipped_inserts": 0,
    "failed_records": 0
  },
  "duration_seconds": 4.2,
  "status": "success"
}
```
CloudWatch metric filters extract `RecordsProcessed`, `DuplicatesRemoved`, and `InvalidRecords`
from this event for dashboards and alarms.

---

## PostgreSQL Schema

```sql
CREATE TABLE sales_records (
    id           SERIAL PRIMARY KEY,
    order_id     VARCHAR(50)    NOT NULL,
    customer_id  VARCHAR(50)    NOT NULL,
    product_id   VARCHAR(50)    NOT NULL,
    product_name VARCHAR(255)   NOT NULL,
    category     VARCHAR(100),
    quantity     INTEGER        NOT NULL CHECK (quantity > 0),
    unit_price   NUMERIC(10,2)  NOT NULL CHECK (unit_price >= 0),
    total_price  NUMERIC(10,2)  NOT NULL CHECK (total_price >= 0),
    order_date   DATE           NOT NULL,
    region       VARCHAR(100),
    source_file  VARCHAR(500),
    processed_at TIMESTAMP      NOT NULL DEFAULT NOW()
);

-- Idempotency index
CREATE UNIQUE INDEX uix_sales_order_product ON sales_records (order_id, product_id);
```

Schema is auto-created by `scripts/init_schema.py` in the CI configure stage.

---

## Local Execution with Docker Compose

### Prerequisites
- Docker and Docker Compose installed
- AWS credentials with S3 access (for CSV upload/download)

### Steps

**1. Copy environment file:**
```bash
cp .env.example .env
# Edit .env — fill in AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, S3_BUCKET
```

**2. Start PostgreSQL and initialise schema:**
```bash
docker compose up postgres init-schema
```

**3. Upload the sample CSV to your S3 bucket:**
```bash
aws s3 cp data/sample_sales.csv s3://<your-bucket>/input/sample_sales.csv
```

**4. Run the ETL pipeline:**
```bash
docker compose up --build etl
```

**5. Check the results:**
```bash
docker compose exec postgres psql -U etladmin -d salesdb \
  -c "SELECT COUNT(*), SUM(total_price) FROM sales_records;"
```

**6. Tear down:**
```bash
docker compose down -v
```

### Running tests locally
```bash
pip install -r requirements.txt
pytest tests/ -v --cov=etl --cov-report=term-missing
```

---

## Deployment Steps (AWS via CI/CD)

The GitHub Actions pipeline runs automatically on push to `main`.

### First-time setup

**1. Fork/clone this repository to your GitHub account.**

**2. Set the following repository secrets** (Settings → Secrets → Actions):
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `DB_PASSWORD` — alphanumeric, ≥ 20 chars, no special characters
- `TF_STATE_BUCKET` — your Terraform state S3 bucket
- `PROJECT_NAME` — e.g. `etl-sales-pipeline`

**3. Push to `main`** — the pipeline runs these stages:

| Stage | What it does |
|---|---|
| `lint` | flake8, black, isort |
| `test` | pytest with coverage |
| `build_push` | Docker build → ECR push (tagged with commit SHA) |
| `provision` | Terraform: VPC, S3, ECR, RDS, ECS, EventBridge, CloudWatch, IAM |
| `configure` | DB schema init, sample CSV upload, EventBridge schedule confirmation |
| `verify` | ECS task definition active, S3 accessible, RDS reachable, test ETL run |

### Manual ETL trigger (any time after deploy)
```bash
# Get cluster name and task definition from Terraform outputs
CLUSTER=$(terraform -chdir=infra output -raw ecs_cluster_name)
TASK_DEF=$(terraform -chdir=infra output -raw ecs_task_definition_arn)
SUBNET=$(terraform -chdir=infra output -raw private_subnet_id)
TASK_SG=$(terraform -chdir=infra output -raw ecs_task_sg_id)

aws ecs run-task \
  --cluster "$CLUSTER" \
  --task-definition "$TASK_DEF" \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNET],securityGroups=[$TASK_SG],assignPublicIp=DISABLED}"
```

### Upload a new CSV for processing
```bash
BUCKET=$(terraform -chdir=infra output -raw s3_bucket_name)
aws s3 cp my-sales-data.csv s3://$BUCKET/input/my-sales-data.csv
```
The next scheduled run (02:00 UTC) will pick it up automatically, or trigger manually above.

### Change the schedule
Update `variable "etl_schedule"` in `infra/variables.tf` and push — Terraform will update
the EventBridge Scheduler expression on the next deploy.

---

## Configuration Reference

| Variable | Required | Default | Description |
|---|---|---|---|
| `S3_BUCKET` | ✅ | — | S3 landing bucket name |
| `DB_HOST` | ✅ | — | RDS endpoint hostname |
| `DB_USER` | ✅ | — | Database username |
| `DB_PASSWORD` | ✅ | — | Database password (from Secrets Manager in ECS) |
| `AWS_DEFAULT_REGION` | | `us-east-1` | AWS region |
| `S3_INPUT_PREFIX` | | `input/` | S3 prefix for incoming CSVs |
| `S3_PROCESSED_PREFIX` | | `processed/` | S3 prefix for successful runs |
| `S3_FAILED_PREFIX` | | `failed/` | S3 prefix for failed runs |
| `DB_PORT` | | `5432` | PostgreSQL port |
| `DB_NAME` | | `salesdb` | Database name |
| `DB_SSL_MODE` | | `require` | SSL mode (`disable` for local) |
| `BATCH_SIZE` | | `500` | Insert batch size |
| `MAX_RETRIES` | | `3` | Max retries per stage |
| `RETRY_DELAY_SECONDS` | | `5` | Initial retry delay (doubles each attempt) |
| `LOG_LEVEL` | | `INFO` | Logging level |
| `S3_KEY` | | — | Explicit S3 key to process (overrides auto-select) |

---

## CloudWatch Monitoring

### Log group
All structured JSON logs are streamed to:
```
/ecs/etl-sales-pipeline
```

### Metric filters (namespace: `etl-sales-pipeline/ETL`)
| Metric | Filter |
|---|---|
| `RecordsProcessed` | `{ $.event = "quality_report" }` → `$.records.successful_inserts` |
| `DuplicatesRemoved` | `{ $.event = "quality_report" }` → `$.records.duplicates_removed` |
| `InvalidRecords` | `{ $.event = "quality_report" }` → `$.records.invalid_records` |
| `ETLErrors` | `{ $.level = "ERROR" }` |
| `PipelineFailures` | `{ $.event = "pipeline_failed" }` |

### Alarms provisioned
- `etl-sales-pipeline-etl-errors` — any ERROR log entry
- `etl-sales-pipeline-pipeline-failure` — any pipeline failure event
- `etl-sales-pipeline-rds-cpu` — RDS CPU > 80%
- `etl-sales-pipeline-rds-storage` — RDS free storage < 2 GB

### View logs (CLI)
```bash
LOG_GROUP=$(terraform -chdir=infra output -raw cloudwatch_log_group)
aws logs tail "$LOG_GROUP" --follow
```

---

## Troubleshooting

### ETL task exits with code 1
1. Check CloudWatch logs: `aws logs tail /ecs/etl-sales-pipeline --follow`
2. Look for `"event": "pipeline_failed"` or `"level": "ERROR"` entries
3. The failed CSV will have been moved to `s3://<bucket>/failed/`

### No input files found
The pipeline exits 0 (not a failure) if no CSVs are in `input/`. Upload one:
```bash
aws s3 cp data/sample_sales.csv s3://<bucket>/input/sample_sales.csv
```

### RDS connection refused
- Confirm ECS task SG has egress on port 5432
- Confirm RDS SG allows ingress from ECS task SG on port 5432
- Check `terraform output rds_endpoint` matches `DB_HOST` in the task definition

### Permission denied on S3
- Check ECS task role policy: `s3:GetObject`, `s3:PutObject` on the landing bucket ARN
- Run: `aws iam simulate-principal-policy` to test the role

### Duplicate rows accumulating
This should not happen — the `UNIQUE INDEX ON (order_id, product_id)` + `ON CONFLICT DO NOTHING`
prevents it. If you see duplicates, check that the same unique index exists:
```sql
SELECT indexname FROM pg_indexes WHERE tablename = 'sales_records';
```

### Changing the cron schedule
Edit `variable "etl_schedule"` in `infra/variables.tf`:
```hcl
default = "cron(0 6 * * ? *)"  # 06:00 UTC
```
Push to `main` — the EventBridge Scheduler is updated by Terraform on the next deploy.

---

## Project Structure

```
etl-sales-pipeline/
├── etl/
│   ├── __init__.py
│   ├── config.py          # Environment-based configuration
│   ├── logger.py          # Structured JSON logger
│   ├── extract.py         # Stage 1: S3 CSV download
│   ├── transform.py       # Stage 2: clean, validate, TotalPrice
│   ├── load.py            # Stage 3: idempotent PostgreSQL upsert
│   ├── pipeline.py        # Orchestrator: Extract→Transform→Load
│   └── quality_report.py  # Data quality report emission
├── scripts/
│   └── init_schema.py     # DB schema initialisation (CI configure stage)
├── tests/
│   ├── test_extract.py
│   ├── test_transform.py
│   └── test_load.py
├── infra/                 # Terraform IaC (AWS)
│   ├── versions.tf
│   ├── variables.tf
│   ├── networking.tf      # VPC, subnets, NAT Gateway, security groups
│   ├── s3.tf              # S3 landing bucket
│   ├── ecr.tf             # ECR repository
│   ├── rds.tf             # RDS PostgreSQL
│   ├── ecs.tf             # ECS cluster + task definition
│   ├── iam.tf             # IAM roles + Secrets Manager
│   ├── cloudwatch.tf      # Log group, metric filters, alarms
│   ├── eventbridge.tf     # EventBridge Scheduler
│   └── outputs.tf
├── data/
│   └── sample_sales.csv   # 50-row test dataset (includes invalid + duplicate rows)
├── .udap/
│   ├── architecture.d2    # Architecture source of truth
│   └── pipeline.yaml      # CI/CD pipeline spec
├── main.py                # Container entrypoint
├── Dockerfile             # Multi-stage Python 3.11-slim image
├── docker-compose.yml     # Local development
├── .env.example           # Environment variable reference
├── requirements.txt       # Pinned Python dependencies
└── README.md
```
