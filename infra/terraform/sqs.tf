# Dead-letter queue for failed Lambda invocations.
resource "aws_sqs_queue" "lambda_dlq" {
  name                      = "${var.project}-lambda-dlq"
  message_retention_seconds = 1209600
}
