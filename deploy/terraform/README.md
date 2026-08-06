# Institutional Reasoning Engine Staging Infrastructure (Terraform)

This Terraform module provisions one AWS environment for the API and worker tier. Use it separately in the demo, staging, or a dedicated production tenant account; do not put public, demo, staging, provider operations, and tenant production into one undifferentiated AWS account.

It creates private application/data subnets, HTTPS-only API ingress, ECS Fargate, encrypted RDS and Redis, an SQS worker-signal queue and DLQ, a private versioned evidence bucket, KMS, Secrets Manager, and task roles.

## Architecture
- **Compute:** AWS ECS (Fargate) for the FastAPI backend.
- **Database:** Amazon RDS (PostgreSQL) in a private subnet.
- **Durable job ledger:** PostgreSQL `background_jobs`, written atomically with source-state transitions.
- **Worker wakeup:** Amazon SQS signal queue and DLQ. Messages contain identifiers only; they are not the authoritative job record.
- **Cache/Idempotency:** Amazon ElastiCache (Redis), not the durable queue.
- **Storage:** Amazon S3 (Private, Versioned) for handbook and evidence storage.
- **Networking:** VPC with public/private subnets, NAT Gateway, and HTTPS-only Application Load Balancer (ALB).
- **Secrets:** AWS Secrets Manager for database credentials and OIDC keys.

## Prerequisites
- Terraform >= 1.5.0
- AWS CLI configured with appropriate permissions.
- A registered domain name and ACM certificate for HTTPS ingress.

## Usage
1. Build and push an immutable API image, then copy `terraform.tfvars.example` to `terraform.tfvars` and populate it only through the institution's secure CI secret store.
2. Copy `backend.hcl.example` to `backend.hcl` and populate it with the institution-owned, encrypted remote-state location.
3. Run `terraform init -backend-config=backend.hcl`
4. Run `terraform plan` to review the changes. Do not commit the generated plan.
5. Run `terraform apply` to provision the infrastructure.

## Security Controls
- **No Public Database Access:** RDS and Redis are deployed in private subnets.
- **Encryption:** S3 and RDS use a customer-managed KMS key; Redis encrypts at rest and in transit.
- **Evidence storage:** S3 versioning, public-access blocking, KMS encryption, and incomplete-upload cleanup are enabled. Object Lock must be approved and configured separately because it changes retention/deletion obligations.
- **Worker queue safety:** API tasks can publish SQS wakeup signals. Worker tasks can receive and delete those signals. Workers still claim work through tenant-scoped PostgreSQL leases.
- **Least privilege:** The application task can access only the runtime secrets, KMS key, evidence objects, and background-job signal queue required by the runtime. The AWS account and state bucket remain institution-controlled.

## Release Gates

Do not apply this stack until ICTS has supplied the ACM certificate, DNS zone, OIDC contract, container registry/image, encrypted remote Terraform state, backup ownership, evidence-retention decision, and incident contacts. Run Alembic migrations through a separate migration role before deploying the ECS service; the serving role must pass the application's PostgreSQL RLS startup checks. This module provisions the API and worker tier; the separately built frontend still needs an institution-approved static-hosting or portal-integration route.

See `docs/AWS_PLATFORM_ARCHITECTURE.md` for the broader AWS Organizations, public/demo/staging/provider/tenant, central logging, and backup account model.
