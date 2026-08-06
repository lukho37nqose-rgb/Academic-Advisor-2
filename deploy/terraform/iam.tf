# ──────────────────────────────────────────────────────────────────────────────
# IAM Roles for ECS Fargate
# ──────────────────────────────────────────────────────────────────────────────

# --- ECS Task Execution Role (ECR pull, logs, secrets) ---

data "aws_iam_policy_document" "ecs_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ecs_execution" {
  name               = "${local.name}-ecs-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json

  tags = local.tags
}

resource "aws_iam_role_policy_attachment" "ecs_execution_managed" {
  role       = aws_iam_role.ecs_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "execution_extras" {
  statement {
    sid    = "ReadSecrets"
    effect = "Allow"
    actions = [
      "secretsmanager:GetSecretValue",
    ]
    resources = [
      aws_secretsmanager_secret.app.arn,
      aws_secretsmanager_secret.db_connection.arn,
    ]
  }

  statement {
    sid    = "DecryptWithKMS"
    effect = "Allow"
    actions = [
      "kms:Decrypt",
    ]
    resources = [aws_kms_key.main.arn]
  }
}

resource "aws_iam_role_policy" "execution_extras" {
  name   = "${local.name}-execution-extras"
  role   = aws_iam_role.ecs_execution.id
  policy = data.aws_iam_policy_document.execution_extras.json
}

# --- ECS Task Role (application-level permissions) ---

resource "aws_iam_role" "ecs_task" {
  name               = "${local.name}-ecs-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json

  tags = local.tags
}

data "aws_iam_policy_document" "task_permissions" {
  statement {
    sid    = "S3Evidence"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:ListBucket",
    ]
    resources = [
      aws_s3_bucket.evidence.arn,
      "${aws_s3_bucket.evidence.arn}/*",
    ]
  }

  statement {
    sid    = "KMSForS3"
    effect = "Allow"
    actions = [
      "kms:Decrypt",
      "kms:GenerateDataKey",
    ]
    resources = [aws_kms_key.main.arn]
  }

  statement {
    sid    = "SQSPublishBackgroundJobSignals"
    effect = "Allow"
    actions = [
      "sqs:GetQueueAttributes",
      "sqs:SendMessage",
    ]
    resources = [aws_sqs_queue.background_jobs.arn]
  }
}

resource "aws_iam_role_policy" "task_permissions" {
  name   = "${local.name}-task-permissions"
  role   = aws_iam_role.ecs_task.id
  policy = data.aws_iam_policy_document.task_permissions.json
}

# --- Worker Task Role (background processing + SQS signal consumption) ---

resource "aws_iam_role" "ecs_worker_task" {
  name               = "${local.name}-ecs-worker-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json

  tags = local.tags
}

data "aws_iam_policy_document" "worker_task_permissions" {
  statement {
    sid    = "S3Evidence"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:ListBucket",
    ]
    resources = [
      aws_s3_bucket.evidence.arn,
      "${aws_s3_bucket.evidence.arn}/*",
    ]
  }

  statement {
    sid    = "KMSForS3AndSQS"
    effect = "Allow"
    actions = [
      "kms:Decrypt",
      "kms:GenerateDataKey",
    ]
    resources = [aws_kms_key.main.arn]
  }

  statement {
    sid    = "SQSConsumeBackgroundJobSignals"
    effect = "Allow"
    actions = [
      "sqs:ChangeMessageVisibility",
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes",
      "sqs:ReceiveMessage",
    ]
    resources = [aws_sqs_queue.background_jobs.arn]
  }
}

resource "aws_iam_role_policy" "worker_task_permissions" {
  name   = "${local.name}-worker-task-permissions"
  role   = aws_iam_role.ecs_worker_task.id
  policy = data.aws_iam_policy_document.worker_task_permissions.json
}

# --- EventBridge Role (for scheduled tasks) ---

data "aws_iam_policy_document" "eventbridge_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["events.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "eventbridge_ecs" {
  name               = "${local.name}-eventbridge-ecs"
  assume_role_policy = data.aws_iam_policy_document.eventbridge_assume.json

  tags = local.tags
}

data "aws_iam_policy_document" "eventbridge_ecs_policy" {
  statement {
    effect    = "Allow"
    actions   = ["ecs:RunTask"]
    resources = ["*"]
    condition {
      test     = "ArnEquals"
      variable = "ecs:cluster"
      values   = [aws_ecs_cluster.main.arn]
    }
  }

  statement {
    effect  = "Allow"
    actions = ["iam:PassRole"]
    resources = [
      aws_iam_role.ecs_execution.arn,
      aws_iam_role.ecs_task.arn
    ]
  }
}

resource "aws_iam_role_policy" "eventbridge_ecs_policy" {
  name   = "${local.name}-eventbridge-ecs-policy"
  role   = aws_iam_role.eventbridge_ecs.id
  policy = data.aws_iam_policy_document.eventbridge_ecs_policy.json
}
