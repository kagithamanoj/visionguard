output "incoming_bucket" {
  value = aws_s3_bucket.incoming.bucket
}

output "quarantine_bucket" {
  value = aws_s3_bucket.quarantine.bucket
}

output "verdicts_bucket" {
  value = aws_s3_bucket.verdicts.bucket
}

output "api_endpoint" {
  value = aws_apigatewayv2_api.http.api_endpoint
}

output "audit_table" {
  value = aws_dynamodb_table.audit.name
}
