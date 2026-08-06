# ──────────────────────────────────────────────────────────────────────────────
# Outputs
# ──────────────────────────────────────────────────────────────────────────────

output "api_url" {
  description = "Public HTTPS URL for the API"
  value       = "https://${var.api_hostname}"
}

output "alb_dns_name" {
  description = "ALB DNS name (for verification / CNAME fallback)"
  value       = aws_lb.api.dns_name
}

output "ecr_repository_url" {
  description = "ECR repository URL for CI/CD image push"
  value       = aws_ecr_repository.api.repository_url
}

output "ecs_cluster_name" {
  description = "ECS cluster name (for deploy scripts)"
  value       = aws_ecs_cluster.main.name
}

output "ecs_service_name" {
  description = "ECS service name (for deploy scripts)"
  value       = aws_ecs_service.api.name
}

output "rds_endpoint" {
  description = "RDS PostgreSQL endpoint"
  value       = aws_db_instance.main.endpoint
  sensitive   = true
}

output "redis_endpoint" {
  description = "ElastiCache Redis primary endpoint"
  value       = aws_elasticache_replication_group.main.primary_endpoint_address
  sensitive   = true
}

output "background_job_signal_queue_url" {
  description = "SQS URL for background job wakeup signals"
  value       = aws_sqs_queue.background_jobs.url
  sensitive   = true
}

output "background_job_signal_dlq_arn" {
  description = "SQS DLQ ARN for failed background job wakeup signals"
  value       = aws_sqs_queue.background_jobs_dlq.arn
}

output "evidence_bucket_name" {
  description = "S3 bucket for evidence artifacts"
  value       = aws_s3_bucket.evidence.id
}

output "database_url_secret_arn" {
  description = "Secrets Manager ARN for the application database URL"
  value       = aws_secretsmanager_secret.db_connection.arn
  sensitive   = true
}

output "app_secrets_arn" {
  description = "Secrets Manager ARN for application runtime secrets"
  value       = aws_secretsmanager_secret.app.arn
}
