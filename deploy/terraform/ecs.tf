# ──────────────────────────────────────────────────────────────────────────────
# ECS Cluster + Fargate Service + CloudWatch Logs
# ──────────────────────────────────────────────────────────────────────────────

resource "aws_cloudwatch_log_group" "api" {
  name              = "/ecs/${local.name}/api"
  retention_in_days = 30
  kms_key_id        = aws_kms_key.main.arn

  tags = local.tags
}

resource "aws_ecs_cluster" "main" {
  name = local.name

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  configuration {
    execute_command_configuration {
      kms_key_id = aws_kms_key.main.arn
      logging    = "OVERRIDE"

      log_configuration {
        cloud_watch_log_group_name = aws_cloudwatch_log_group.api.name
      }
    }
  }

  tags = local.tags
}

resource "aws_ecs_task_definition" "api" {
  family                   = "${local.name}-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.api_cpu
  memory                   = var.api_memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name      = "api"
      image     = var.api_image
      essential = true

      portMappings = [
        {
          containerPort = 8000
          hostPort      = 8000
          protocol      = "tcp"
        }
      ]

      environment = [
        { name = "IRE_ENV", value = var.environment },
        { name = "IRE_AUTO_CREATE_SCHEMA", value = "false" },
        { name = "REDIS_URL", value = "rediss://${aws_elasticache_replication_group.main.primary_endpoint_address}:6379/0" },
        { name = "IRE_BACKGROUND_JOB_SIGNAL_QUEUE_URL", value = aws_sqs_queue.background_jobs.url },
        { name = "S3_BUCKET_NAME", value = aws_s3_bucket.evidence.id },
        { name = "S3_SERVER_SIDE_ENCRYPTION", value = "aws:kms" },
        { name = "AWS_REGION", value = var.aws_region },
      ]

      secrets = [
        { name = "DATABASE_URL", valueFrom = aws_secretsmanager_secret.db_connection.arn },
        { name = "JWT_JWKS_URL", valueFrom = "${aws_secretsmanager_secret.app.arn}:JWT_JWKS_URL::" },
        { name = "JWT_ISSUER", valueFrom = "${aws_secretsmanager_secret.app.arn}:JWT_ISSUER::" },
        { name = "JWT_AUDIENCE", valueFrom = "${aws_secretsmanager_secret.app.arn}:JWT_AUDIENCE::" },
        { name = "JWT_SECRET_KEY", valueFrom = "${aws_secretsmanager_secret.app.arn}:JWT_SECRET_KEY::" },
        { name = "PUBLIC_RATE_LIMIT_SALT", valueFrom = "${aws_secretsmanager_secret.app.arn}:PUBLIC_RATE_LIMIT_SALT::" },
        { name = "GOVERNANCE_PRIVATE_KEY", valueFrom = "${aws_secretsmanager_secret.app.arn}:GOVERNANCE_PRIVATE_KEY::" },
        { name = "GOVERNANCE_KEY_ID", valueFrom = "${aws_secretsmanager_secret.app.arn}:GOVERNANCE_KEY_ID::" },
        { name = "IRE_TENANT_CLAIM", valueFrom = "${aws_secretsmanager_secret.app.arn}:IRE_TENANT_CLAIM::" },
        { name = "IRE_ROLE_CLAIM", valueFrom = "${aws_secretsmanager_secret.app.arn}:IRE_ROLE_CLAIM::" },
        { name = "IRE_DOMAIN_IDS_CLAIM", valueFrom = "${aws_secretsmanager_secret.app.arn}:IRE_DOMAIN_IDS_CLAIM::" },
        { name = "IRE_SUBJECT_ID_CLAIM", valueFrom = "${aws_secretsmanager_secret.app.arn}:IRE_SUBJECT_ID_CLAIM::" },
        { name = "IRE_PROVIDER_JWKS_URL", valueFrom = "${aws_secretsmanager_secret.app.arn}:IRE_PROVIDER_JWKS_URL::" },
        { name = "IRE_PROVIDER_ISSUER", valueFrom = "${aws_secretsmanager_secret.app.arn}:IRE_PROVIDER_ISSUER::" },
        { name = "IRE_PROVIDER_AUDIENCE", valueFrom = "${aws_secretsmanager_secret.app.arn}:IRE_PROVIDER_AUDIENCE::" },
        { name = "IRE_PROVIDER_ROLE_CLAIM", valueFrom = "${aws_secretsmanager_secret.app.arn}:IRE_PROVIDER_ROLE_CLAIM::" },
        { name = "IRE_CORS_ALLOWED_ORIGINS", valueFrom = "${aws_secretsmanager_secret.app.arn}:IRE_CORS_ALLOWED_ORIGINS::" }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.api.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "api"
        }
      }

      healthCheck = {
        command     = ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=3)\" || exit 1"]
        interval    = 30
        timeout     = 5
        startPeriod = 20
        retries     = 3
      }
    }
  ])

  tags = local.tags
}

resource "aws_ecs_service" "api" {
  name            = "${local.name}-api"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = var.api_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = [for s in aws_subnet.private : s.id]
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = 8000
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  deployment_maximum_percent         = 200
  deployment_minimum_healthy_percent = 100

  depends_on = [aws_lb_listener.http]

  tags = local.tags

  lifecycle {
    ignore_changes = [desired_count]
  }
}

# ──────────────────────────────────────────────────────────────────────────────
# Worker (background tasks – same image, different entrypoint)
# ──────────────────────────────────────────────────────────────────────────────

resource "aws_cloudwatch_log_group" "worker" {
  name              = "/ecs/${local.name}/worker"
  retention_in_days = 30
  kms_key_id        = aws_kms_key.main.arn

  tags = local.tags
}

resource "aws_ecs_task_definition" "worker" {
  family                   = "${local.name}-worker"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.api_cpu
  memory                   = var.api_memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_worker_task.arn

  container_definitions = jsonencode([
    {
      name      = "worker"
      image     = var.api_image
      essential = true

      command = ["python", "-m", "app.services.background_worker"]

      environment = [
        { name = "IRE_ENV", value = var.environment },
        { name = "REDIS_URL", value = "rediss://${aws_elasticache_replication_group.main.primary_endpoint_address}:6379/0" },
        { name = "IRE_BACKGROUND_JOB_SIGNAL_QUEUE_URL", value = aws_sqs_queue.background_jobs.url },
        { name = "S3_BUCKET_NAME", value = aws_s3_bucket.evidence.id },
        { name = "S3_SERVER_SIDE_ENCRYPTION", value = "aws:kms" },
        { name = "AWS_REGION", value = var.aws_region },
        { name = "IRE_WORKER_TENANT_IDS", value = var.worker_tenant_ids },
      ]

      secrets = [
        { name = "DATABASE_URL", valueFrom = aws_secretsmanager_secret.db_connection.arn },
        { name = "JWT_JWKS_URL", valueFrom = "${aws_secretsmanager_secret.app.arn}:JWT_JWKS_URL::" },
        { name = "JWT_ISSUER", valueFrom = "${aws_secretsmanager_secret.app.arn}:JWT_ISSUER::" },
        { name = "JWT_AUDIENCE", valueFrom = "${aws_secretsmanager_secret.app.arn}:JWT_AUDIENCE::" },
        { name = "JWT_SECRET_KEY", valueFrom = "${aws_secretsmanager_secret.app.arn}:JWT_SECRET_KEY::" },
        { name = "PUBLIC_RATE_LIMIT_SALT", valueFrom = "${aws_secretsmanager_secret.app.arn}:PUBLIC_RATE_LIMIT_SALT::" },
        { name = "GOVERNANCE_PRIVATE_KEY", valueFrom = "${aws_secretsmanager_secret.app.arn}:GOVERNANCE_PRIVATE_KEY::" },
        { name = "GOVERNANCE_KEY_ID", valueFrom = "${aws_secretsmanager_secret.app.arn}:GOVERNANCE_KEY_ID::" },
        { name = "IRE_TENANT_CLAIM", valueFrom = "${aws_secretsmanager_secret.app.arn}:IRE_TENANT_CLAIM::" },
        { name = "IRE_ROLE_CLAIM", valueFrom = "${aws_secretsmanager_secret.app.arn}:IRE_ROLE_CLAIM::" },
        { name = "IRE_DOMAIN_IDS_CLAIM", valueFrom = "${aws_secretsmanager_secret.app.arn}:IRE_DOMAIN_IDS_CLAIM::" },
        { name = "IRE_SUBJECT_ID_CLAIM", valueFrom = "${aws_secretsmanager_secret.app.arn}:IRE_SUBJECT_ID_CLAIM::" },
        { name = "IRE_CORS_ALLOWED_ORIGINS", valueFrom = "${aws_secretsmanager_secret.app.arn}:IRE_CORS_ALLOWED_ORIGINS::" }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.worker.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "worker"
        }
      }
    }
  ])

  tags = local.tags
}

resource "aws_ecs_service" "worker" {
  name            = "${local.name}-worker"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.worker.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = [for s in aws_subnet.private : s.id]
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = false
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  tags = local.tags

  lifecycle {
    ignore_changes = [desired_count]
  }
}

# ──────────────────────────────────────────────────────────────────────────────
# Migration (Alembic – one-shot task definition, no persistent service)
# ──────────────────────────────────────────────────────────────────────────────

resource "aws_cloudwatch_log_group" "migration" {
  name              = "/ecs/${local.name}/migration"
  retention_in_days = 30
  kms_key_id        = aws_kms_key.main.arn

  tags = local.tags
}

resource "aws_ecs_task_definition" "migration" {
  family                   = "${local.name}-migration"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name      = "migration"
      image     = var.api_image
      essential = true

      command = ["alembic", "upgrade", "head"]

      environment = [
        { name = "IRE_ENV", value = var.environment },
        { name = "S3_BUCKET_NAME", value = aws_s3_bucket.evidence.id },
        { name = "S3_SERVER_SIDE_ENCRYPTION", value = "aws:kms" },
        { name = "AWS_REGION", value = var.aws_region },
      ]

      secrets = [
        { name = "DATABASE_URL", valueFrom = aws_secretsmanager_secret.db_connection.arn },
        { name = "JWT_JWKS_URL", valueFrom = "${aws_secretsmanager_secret.app.arn}:JWT_JWKS_URL::" },
        { name = "JWT_ISSUER", valueFrom = "${aws_secretsmanager_secret.app.arn}:JWT_ISSUER::" },
        { name = "JWT_AUDIENCE", valueFrom = "${aws_secretsmanager_secret.app.arn}:JWT_AUDIENCE::" },
        { name = "JWT_SECRET_KEY", valueFrom = "${aws_secretsmanager_secret.app.arn}:JWT_SECRET_KEY::" },
        { name = "PUBLIC_RATE_LIMIT_SALT", valueFrom = "${aws_secretsmanager_secret.app.arn}:PUBLIC_RATE_LIMIT_SALT::" },
        { name = "GOVERNANCE_PRIVATE_KEY", valueFrom = "${aws_secretsmanager_secret.app.arn}:GOVERNANCE_PRIVATE_KEY::" },
        { name = "GOVERNANCE_KEY_ID", valueFrom = "${aws_secretsmanager_secret.app.arn}:GOVERNANCE_KEY_ID::" },
        { name = "IRE_TENANT_CLAIM", valueFrom = "${aws_secretsmanager_secret.app.arn}:IRE_TENANT_CLAIM::" },
        { name = "IRE_ROLE_CLAIM", valueFrom = "${aws_secretsmanager_secret.app.arn}:IRE_ROLE_CLAIM::" },
        { name = "IRE_DOMAIN_IDS_CLAIM", valueFrom = "${aws_secretsmanager_secret.app.arn}:IRE_DOMAIN_IDS_CLAIM::" },
        { name = "IRE_SUBJECT_ID_CLAIM", valueFrom = "${aws_secretsmanager_secret.app.arn}:IRE_SUBJECT_ID_CLAIM::" },
        { name = "IRE_CORS_ALLOWED_ORIGINS", valueFrom = "${aws_secretsmanager_secret.app.arn}:IRE_CORS_ALLOWED_ORIGINS::" }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.migration.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "migration"
        }
      }
    }
  ])

  tags = local.tags
}

# ──────────────────────────────────────────────────────────────────────────────
# Retention (Scheduled background task)
# ──────────────────────────────────────────────────────────────────────────────

resource "aws_cloudwatch_log_group" "retention" {
  name              = "/ecs/${local.name}/retention"
  retention_in_days = 30
  kms_key_id        = aws_kms_key.main.arn

  tags = local.tags
}

resource "aws_ecs_task_definition" "retention" {
  family                   = "${local.name}-retention"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name      = "retention"
      image     = var.api_image
      essential = true

      command = ["python", "-m", "app.services.retention"]

      environment = [
        { name = "IRE_ENV", value = var.environment },
        { name = "REDIS_URL", value = "rediss://${aws_elasticache_replication_group.main.primary_endpoint_address}:6379/0" },
        { name = "S3_BUCKET_NAME", value = aws_s3_bucket.evidence.id },
        { name = "S3_SERVER_SIDE_ENCRYPTION", value = "aws:kms" },
        { name = "AWS_REGION", value = var.aws_region },
        { name = "IRE_RETENTION_TENANT_IDS", value = var.worker_tenant_ids },
      ]

      secrets = [
        { name = "DATABASE_URL", valueFrom = aws_secretsmanager_secret.db_connection.arn },
        { name = "JWT_JWKS_URL", valueFrom = "${aws_secretsmanager_secret.app.arn}:JWT_JWKS_URL::" },
        { name = "JWT_ISSUER", valueFrom = "${aws_secretsmanager_secret.app.arn}:JWT_ISSUER::" },
        { name = "JWT_AUDIENCE", valueFrom = "${aws_secretsmanager_secret.app.arn}:JWT_AUDIENCE::" },
        { name = "JWT_SECRET_KEY", valueFrom = "${aws_secretsmanager_secret.app.arn}:JWT_SECRET_KEY::" },
        { name = "PUBLIC_RATE_LIMIT_SALT", valueFrom = "${aws_secretsmanager_secret.app.arn}:PUBLIC_RATE_LIMIT_SALT::" },
        { name = "GOVERNANCE_PRIVATE_KEY", valueFrom = "${aws_secretsmanager_secret.app.arn}:GOVERNANCE_PRIVATE_KEY::" },
        { name = "GOVERNANCE_KEY_ID", valueFrom = "${aws_secretsmanager_secret.app.arn}:GOVERNANCE_KEY_ID::" },
        { name = "IRE_TENANT_CLAIM", valueFrom = "${aws_secretsmanager_secret.app.arn}:IRE_TENANT_CLAIM::" },
        { name = "IRE_ROLE_CLAIM", valueFrom = "${aws_secretsmanager_secret.app.arn}:IRE_ROLE_CLAIM::" },
        { name = "IRE_DOMAIN_IDS_CLAIM", valueFrom = "${aws_secretsmanager_secret.app.arn}:IRE_DOMAIN_IDS_CLAIM::" },
        { name = "IRE_SUBJECT_ID_CLAIM", valueFrom = "${aws_secretsmanager_secret.app.arn}:IRE_SUBJECT_ID_CLAIM::" },
        { name = "IRE_CORS_ALLOWED_ORIGINS", valueFrom = "${aws_secretsmanager_secret.app.arn}:IRE_CORS_ALLOWED_ORIGINS::" }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.retention.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "retention"
        }
      }
    }
  ])

  tags = local.tags
}

resource "aws_cloudwatch_event_rule" "retention_schedule" {
  name                = "${local.name}-retention-schedule"
  description         = "Run retention task daily"
  schedule_expression = "rate(1 day)"
  tags                = local.tags
}

resource "aws_cloudwatch_event_target" "retention_target" {
  rule      = aws_cloudwatch_event_rule.retention_schedule.name
  target_id = "retention"
  arn       = aws_ecs_cluster.main.arn
  role_arn  = aws_iam_role.eventbridge_ecs.arn

  ecs_target {
    task_count          = 1
    task_definition_arn = aws_ecs_task_definition.retention.arn
    launch_type         = "FARGATE"

    network_configuration {
      subnets          = [for s in aws_subnet.private : s.id]
      security_groups  = [aws_security_group.ecs_tasks.id]
      assign_public_ip = false
    }
  }
}
