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

output "cloudwatch_dashboard_url" {
  value = "https://console.aws.amazon.com/cloudwatch/home?region=${var.aws_region}#dashboards:name=${aws_cloudwatch_dashboard.visionguard.dashboard_name}"
}

output "alarm_topic_arn" {
  value = aws_sns_topic.alerts.arn
}
