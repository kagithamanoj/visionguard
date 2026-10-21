# CloudWatch dashboard and alarms for the VisionGuard inspection pipeline.
#
# The inspect Lambda publishes custom metrics into the VisionGuard/Inspection
# namespace (see visionguard/aws/metrics.py); the dashboard graphs them
# alongside the standard AWS/Lambda metrics. Alarm notifications go to the
# SNS topic below; set alarm_notification_email to add an email subscriber.
#
# Alarm destinations, thresholds, and periods are tunables in variables.tf.

resource "aws_sns_topic" "alerts" {
  name = "${var.project}-alerts"
}

resource "aws_sns_topic_subscription" "alert_email" {
  count     = var.alarm_notification_email == "" ? 0 : 1
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alarm_notification_email
}

locals {
  inspect_function_name = aws_lambda_function.inspect.function_name
  api_function_name     = aws_lambda_function.api.function_name

  dashboard_widgets = [
    {
      type   = "metric"
      x      = 0
      y      = 0
      width  = 12
      height = 6
      properties = {
        title  = "Lambda invocations"
        view   = "timeSeries"
        region = var.aws_region
        period = 300
        stat   = "Sum"
        metrics = [
          ["AWS/Lambda", "Invocations", "FunctionName",
            local.inspect_function_name],
          ["AWS/Lambda", "Invocations", "FunctionName",
            local.api_function_name],
        ]
      }
    },
    {
      type   = "metric"
      x      = 12
      y      = 0
      width  = 12
      height = 6
      properties = {
        title  = "Verdict mix"
        view   = "timeSeries"
        region = var.aws_region
        period = 300
        metrics = [
          [{
            expression = "SEARCH('{VisionGuard/Inspection} MetricName=\"VerdictCount\"', 'Sum', 300)"
          }],
        ]
      }
    },
    {
      type   = "metric"
      x      = 0
      y      = 6
      width  = 12
      height = 6
      properties = {
        title  = "Gateway denials"
        view   = "timeSeries"
        region = var.aws_region
        period = 300
        metrics = [
          [{
            expression = "SEARCH('{VisionGuard/Inspection} MetricName=\"GatewayDenial\"', 'Sum', 300)"
          }],
        ]
      }
    },
    {
      type   = "metric"
      x      = 12
      y      = 6
      width  = 12
      height = 6
      properties = {
        title  = "Lambda errors"
        view   = "timeSeries"
        region = var.aws_region
        period = 300
        stat   = "Sum"
        metrics = [
          ["AWS/Lambda", "Errors", "FunctionName",
            local.inspect_function_name],
          ["AWS/Lambda", "Errors", "FunctionName",
            local.api_function_name],
        ]
      }
    },
    {
      type   = "metric"
      x      = 0
      y      = 12
      width  = 12
      height = 6
      properties = {
        title  = "Inspection latency (ms)"
        view   = "timeSeries"
        region = var.aws_region
        period = 300
        metrics = [
          [{
            expression = "SEARCH('{VisionGuard/Inspection} MetricName=\"InspectionLatencyMs\"', 'Average', 300)"
          }],
          ["AWS/Lambda", "Duration", "FunctionName",
            local.inspect_function_name, { stat = "p95" }],
        ]
      }
    },
    {
      type   = "metric"
      x      = 12
      y      = 12
      width  = 12
      height = 6
      properties = {
        title  = "Lambda throttles"
        view   = "timeSeries"
        region = var.aws_region
        period = 300
        stat   = "Sum"
        metrics = [
          ["AWS/Lambda", "Throttles", "FunctionName",
            local.inspect_function_name],
          ["AWS/Lambda", "Throttles", "FunctionName",
            local.api_function_name],
        ]
      }
    },
  ]
}

resource "aws_cloudwatch_dashboard" "visionguard" {
  dashboard_name = var.project
  dashboard_body = jsonencode({
    widgets = local.dashboard_widgets
  })
}

# Fires when critical verdicts pile up: more than the configured number of
# critical verdicts in five minutes. A sustained stream of criticals means
# the line is producing bad plates, so a human should look.
resource "aws_cloudwatch_metric_alarm" "critical_verdict_rate" {
  alarm_name          = "${var.project}-critical-verdict-rate"
  alarm_description   = "Elevated critical verdict rate from the VisionGuard inspect Lambda"
  namespace           = "VisionGuard/Inspection"
  metric_name         = "VerdictCount"
  dimensions          = { Verdict = "critical" }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = var.critical_verdicts_per_5min
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]
}

# Fires on a denial spike: the policy gateway is refusing a large share of
# requests, which usually means a misconfigured tenant or a flood.
resource "aws_cloudwatch_metric_alarm" "gateway_denial_spike" {
  alarm_name          = "${var.project}-gateway-denial-spike"
  alarm_description   = "Elevated policy-gateway denial rate from the VisionGuard inspect Lambda"
  namespace           = "VisionGuard/Inspection"
  metric_name         = "GatewayDenial"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = var.gateway_denials_per_5min
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]
}
