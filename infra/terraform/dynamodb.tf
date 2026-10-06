# Audit table: one row per gateway decision and agent action.
resource "aws_dynamodb_table" "audit" {
  name         = "${var.project}-audit"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "tenant"
  range_key    = "at"

  attribute {
    name = "tenant"
    type = "S"
  }

  attribute {
    name = "at"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }
}
