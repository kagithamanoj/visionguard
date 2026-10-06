# Three buckets: incoming images, quarantined defect images, verdict JSON.
locals {
  bucket_suffix = data.aws_caller_identity.current.account_id
}

resource "aws_s3_bucket" "incoming" {
  bucket        = "${var.project}-incoming-${local.bucket_suffix}"
  force_destroy = true
}

resource "aws_s3_bucket" "quarantine" {
  bucket        = "${var.project}-quarantine-${local.bucket_suffix}"
  force_destroy = true
}

resource "aws_s3_bucket" "verdicts" {
  bucket        = "${var.project}-verdicts-${local.bucket_suffix}"
  force_destroy = true
}

resource "aws_s3_bucket_versioning" "verdicts" {
  bucket = aws_s3_bucket.verdicts.id
  versioning_configuration {
    status = "Enabled"
  }
}

# Incoming uploads trigger the inspection Lambda.
resource "aws_s3_bucket_notification" "incoming" {
  bucket = aws_s3_bucket.incoming.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.inspect.arn
    events              = ["s3:ObjectCreated:*"]
    filter_suffix       = ".png"
  }

  depends_on = [aws_lambda_permission.s3_invoke_inspect]
}
