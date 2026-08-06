# ──────────────────────────────────────────────────────────────────────────────
# Input Variables
# ──────────────────────────────────────────────────────────────────────────────

variable "aws_region" {
  description = "AWS region (af-south-1 is Africa Cape Town)"
  type        = string
  default     = "af-south-1"
}

variable "environment" {
  description = "Deployment environment name"
  type        = string
  default     = "staging"

  validation {
    condition     = contains(["demo", "staging", "production"], var.environment)
    error_message = "environment must be 'demo', 'staging', or 'production'."
  }
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.24.0.0/16"
}

variable "api_image" {
  description = "Fully qualified API container image (ECR URI with digest)"
  type        = string
}

variable "certificate_arn" {
  description = "ACM certificate ARN for HTTPS termination on the ALB"
  type        = string
}

variable "api_hostname" {
  description = "Hostname for the API (e.g. ire-staging.example.ac.za)"
  type        = string
}

variable "hosted_zone_id" {
  description = "Route 53 hosted zone ID for DNS record creation"
  type        = string
}

variable "runtime_secret_values" {
  description = "Map of secret key-value pairs injected into the ECS task via Secrets Manager"
  type        = map(string)
  sensitive   = true
}

# ── RDS ───────────────────────────────────────────────────────────────────────

variable "db_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t3.medium"
}

variable "db_allocated_storage" {
  description = "Allocated storage in GB for the RDS instance"
  type        = number
  default     = 20
}

variable "db_max_allocated_storage" {
  description = "Maximum allocated storage in GB (autoscaling ceiling)"
  type        = number
  default     = 100
}

variable "db_name" {
  description = "PostgreSQL database name"
  type        = string
  default     = "reasoning_engine"
}

# ── ECS ───────────────────────────────────────────────────────────────────────

variable "api_cpu" {
  description = "Fargate task CPU units (1024 = 1 vCPU)"
  type        = number
  default     = 512
}

variable "api_memory" {
  description = "Fargate task memory in MiB"
  type        = number
  default     = 1024
}

variable "api_desired_count" {
  description = "Desired number of API tasks"
  type        = number
  default     = 2
}

# ── Redis ─────────────────────────────────────────────────────────────────────

variable "redis_node_type" {
  description = "ElastiCache Redis node type"
  type        = string
  default     = "cache.t3.micro"
}

# ── Worker ────────────────────────────────────────────────────────────────────

variable "worker_tenant_ids" {
  description = "Comma-separated list of tenant IDs the worker is allowed to process"
  type        = string
  default     = "default-tenant"
}

variable "background_job_visibility_timeout_seconds" {
  description = "SQS visibility timeout for background job wakeup signals"
  type        = number
  default     = 120

  validation {
    condition     = var.background_job_visibility_timeout_seconds >= 30 && var.background_job_visibility_timeout_seconds <= 43200
    error_message = "background_job_visibility_timeout_seconds must be between 30 and 43200."
  }
}

variable "background_job_message_retention_seconds" {
  description = "Retention period for unconsumed background job wakeup signals"
  type        = number
  default     = 345600

  validation {
    condition     = var.background_job_message_retention_seconds >= 60 && var.background_job_message_retention_seconds <= 1209600
    error_message = "background_job_message_retention_seconds must be between 60 and 1209600."
  }
}

variable "background_job_dlq_retention_seconds" {
  description = "Retention period for background job wakeup signals that reach the DLQ"
  type        = number
  default     = 1209600

  validation {
    condition     = var.background_job_dlq_retention_seconds >= 60 && var.background_job_dlq_retention_seconds <= 1209600
    error_message = "background_job_dlq_retention_seconds must be between 60 and 1209600."
  }
}

variable "background_job_max_receive_count" {
  description = "Number of SQS receive attempts before a wakeup signal moves to the DLQ"
  type        = number
  default     = 5

  validation {
    condition     = var.background_job_max_receive_count >= 1 && var.background_job_max_receive_count <= 1000
    error_message = "background_job_max_receive_count must be between 1 and 1000."
  }
}
