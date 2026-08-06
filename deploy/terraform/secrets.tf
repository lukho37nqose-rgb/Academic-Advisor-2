# ──────────────────────────────────────────────────────────────────────────────
# Secrets Manager – Application secrets (KMS-encrypted)
# ──────────────────────────────────────────────────────────────────────────────

resource "aws_secretsmanager_secret" "app" {
  name       = "${local.name}/app-secrets"
  kms_key_id = aws_kms_key.main.arn

  tags = local.tags
}

resource "aws_secretsmanager_secret_version" "app" {
  secret_id     = aws_secretsmanager_secret.app.id
  secret_string = jsonencode(var.runtime_secret_values)
}
