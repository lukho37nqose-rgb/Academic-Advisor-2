# SQS wakeup queue for durable PostgreSQL background jobs.
#
# PostgreSQL remains the authoritative job ledger because jobs are created in
# the same transaction as source-state changes. SQS is a low-latency signal
# channel for workers and a deployment-owned DLQ/monitoring boundary.

resource "aws_sqs_queue" "background_jobs_dlq" {
  name                      = "${local.name}-background-jobs-dlq"
  message_retention_seconds = var.background_job_dlq_retention_seconds
  kms_master_key_id         = aws_kms_key.main.arn

  tags = merge(local.tags, { Name = "${local.name}-background-jobs-dlq" })
}

resource "aws_sqs_queue" "background_jobs" {
  name                       = "${local.name}-background-jobs"
  delay_seconds              = 0
  max_message_size           = 4096
  message_retention_seconds  = var.background_job_message_retention_seconds
  receive_wait_time_seconds  = 20
  visibility_timeout_seconds = var.background_job_visibility_timeout_seconds
  kms_master_key_id          = aws_kms_key.main.arn

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.background_jobs_dlq.arn
    maxReceiveCount     = var.background_job_max_receive_count
  })

  tags = merge(local.tags, { Name = "${local.name}-background-jobs" })
}
