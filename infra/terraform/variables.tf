variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "us-east-1"
}

variable "project" {
  description = "Project name used as a resource prefix"
  type        = string
  default     = "visionguard"
}

variable "lambda_image_uri" {
  description = "ECR image URI for the VisionGuard container (includes opencv, torch, visionguard package)"
  type        = string
}

variable "tenant_rate_limit_per_minute" {
  description = "Default per-tenant inspection rate limit enforced by the policy gateway"
  type        = number
  default     = 60
}

variable "bedrock_model_id" {
  description = "Bedrock vision model used by the optional LLM judge (Nova Lite). The judge stays off unless VISIONGUARD_LLM_JUDGE_ENABLED=true."
  type        = string
  default     = "amazon.nova-lite-v1:0"
}

variable "llm_judge_enabled" {
  description = "Enable the Bedrock LLM judge second opinion in the inspect Lambda. Off by default; the rule-based verdict stands alone."
  type        = bool
  default     = false
}

variable "alarm_notification_email" {
  description = "Email address subscribed to the CloudWatch alarm SNS topic. Empty means the topic has no email subscriber."
  type        = string
  default     = ""
}

variable "critical_verdicts_per_5min" {
  description = "Number of critical verdicts in 5 minutes that fires the elevated-critical-rate alarm."
  type        = number
  default     = 10
}

variable "gateway_denials_per_5min" {
  description = "Number of gateway denials in 5 minutes that fires the denial-spike alarm."
  type        = number
  default     = 30
}
