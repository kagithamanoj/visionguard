# Two Lambda functions share one container image; only the CMD differs.
#
# Build the image from the repo root, e.g.:
#   docker build -f infra/docker/Dockerfile -t visionguard .
#   (see infra/terraform/README note in docs/architecture.md)

resource "aws_lambda_function" "inspect" {
  function_name = "${var.project}-inspect"
  role          = aws_iam_role.lambda_exec.arn
  package_type  = "Image"
  image_uri     = var.lambda_image_uri
  image_config {
    command = ["visionguard.aws.lambda_handler.handler"]
  }
  timeout     = 120
  memory_size = 1024

  dead_letter_config {
    target_arn = aws_sqs_queue.lambda_dlq.arn
  }

  environment {
    variables = {
      VERDICTS_BUCKET   = aws_s3_bucket.verdicts.bucket
      QUARANTINE_BUCKET = aws_s3_bucket.quarantine.bucket
      TENANT            = "default"
    }
  }
}

resource "aws_lambda_function" "api" {
  function_name = "${var.project}-api"
  role          = aws_iam_role.lambda_exec.arn
  package_type  = "Image"
  image_uri     = var.lambda_image_uri
  image_config {
    command = ["visionguard.aws.api_handler.handler"]
  }
  timeout     = 60
  memory_size = 1024

  dead_letter_config {
    target_arn = aws_sqs_queue.lambda_dlq.arn
  }
}

resource "aws_lambda_permission" "s3_invoke_inspect" {
  statement_id  = "AllowS3Invoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.inspect.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.incoming.arn
}

resource "aws_lambda_permission" "apigw_invoke_api" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http.execution_arn}/*/*"
}
