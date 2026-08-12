locals {
  intake_table = "${var.project}-${var.environment}-intake"
}

# Intake ("scoped quote") submissions. Every row shares one partition (PK =
# "INTAKE") with a time-ordered sort key so the admin console can list newest-
# first with a cheap Query. Volume is tiny; a single partition is fine.
resource "aws_dynamodb_table" "intake" {
  name         = local.intake_table
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "PK"
  range_key    = "SK"

  attribute {
    name = "PK"
    type = "S"
  }
  attribute {
    name = "SK"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  tags = var.tags
}
