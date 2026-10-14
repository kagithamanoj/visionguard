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
