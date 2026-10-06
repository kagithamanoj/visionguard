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
