# ──────────────────────────────────────────────────────────────────────────────
# RDS PostgreSQL 15 (private subnets, KMS-encrypted, autoscaling storage)
# ──────────────────────────────────────────────────────────────────────────────

resource "aws_db_subnet_group" "main" {
  name       = "${local.name}-db"
  subnet_ids = [for s in aws_subnet.private : s.id]

  tags = merge(local.tags, { Name = "${local.name}-db-subnet-group" })
}

resource "random_password" "db_master" {
  length  = 32
  special = false # avoid shell-escaping issues
}

resource "aws_secretsmanager_secret" "db_connection" {
  name       = "${local.name}/database-url"
  kms_key_id = aws_kms_key.main.arn

  tags = local.tags
}

resource "aws_db_instance" "main" {
  identifier = "${local.name}-pg"

  engine         = "postgres"
  engine_version = "15"

  instance_class        = var.db_instance_class
  allocated_storage     = var.db_allocated_storage
  max_allocated_storage = var.db_max_allocated_storage
  storage_encrypted     = true
  kms_key_id            = aws_kms_key.main.arn

  db_name  = var.db_name
  username = "ire_admin"
  password = random_password.db_master.result

  multi_az               = var.environment == "production"
  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]

  backup_retention_period   = 7
  backup_window             = "02:00-03:00"
  maintenance_window        = "sun:04:00-sun:05:00"
  copy_tags_to_snapshot     = true
  skip_final_snapshot       = var.environment != "production"
  final_snapshot_identifier = var.environment == "production" ? "${local.name}-final-snapshot" : null
  deletion_protection       = var.environment == "production"

  performance_insights_enabled    = true
  performance_insights_kms_key_id = aws_kms_key.main.arn

  apply_immediately = var.environment != "production"

  tags = local.tags
}

# ECS injects this value as a task secret rather than exposing it in its
# environment definition. The remote Terraform state remains sensitive and
# must be institution-owned, encrypted, and tightly access-controlled.
resource "aws_secretsmanager_secret_version" "db_connection" {
  secret_id     = aws_secretsmanager_secret.db_connection.id
  secret_string = "postgresql+asyncpg://${aws_db_instance.main.username}:${random_password.db_master.result}@${aws_db_instance.main.endpoint}/${aws_db_instance.main.db_name}"
}
