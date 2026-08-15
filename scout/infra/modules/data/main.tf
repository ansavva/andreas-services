locals {
  name_prefix = "${var.project}-${var.environment}"

  core_table     = "${local.name_prefix}-core"
  settings_table = "${local.name_prefix}-settings"
}

# Single core table holding the connected entity graph: sources, source-runs,
# events, sub-events, locations, the three label taxonomies, and all M2M
# junction items. Items are keyed by a generic PK/SK; five shared GSIs serve the
# status/queue + public-date, entity->labels, dedup, source-health, and
# deleted-filter access patterns. All GSIs project ALL (cheap at this volume).
resource "aws_dynamodb_table" "core" {
  name         = local.core_table
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
  attribute {
    name = "GSI1PK"
    type = "S"
  }
  attribute {
    name = "GSI1SK"
    type = "S"
  }
  attribute {
    name = "GSI2PK"
    type = "S"
  }
  attribute {
    name = "GSI2SK"
    type = "S"
  }
  attribute {
    name = "GSI3PK"
    type = "S"
  }
  attribute {
    name = "GSI3SK"
    type = "S"
  }
  attribute {
    name = "GSI4PK"
    type = "S"
  }
  attribute {
    name = "GSI4SK"
    type = "S"
  }
  attribute {
    name = "GSI5PK"
    type = "S"
  }
  attribute {
    name = "GSI5SK"
    type = "S"
  }

  # GSI1 — admin status queues (REVIEW#<status>) + public visibility/date order
  # (PUBVIS, sparse: present only while published, not cancelled, not deleted).
  global_secondary_index {
    name            = "GSI1"
    hash_key        = "GSI1PK"
    range_key       = "GSI1SK"
    projection_type = "ALL"
  }

  # GSI2 — entity->labels reverse index (label display + query-time inheritance).
  global_secondary_index {
    name            = "GSI2"
    hash_key        = "GSI2PK"
    range_key       = "GSI2SK"
    projection_type = "ALL"
  }

  # GSI3 — duplicate-detection (DUP#<dup_key>), sparse over live events only.
  global_secondary_index {
    name            = "GSI3"
    hash_key        = "GSI3PK"
    range_key       = "GSI3SK"
    projection_type = "ALL"
  }

  # GSI4 — source health (SRCHEALTH by last_run_at) for the overdue sweep.
  global_secondary_index {
    name            = "GSI4"
    hash_key        = "GSI4PK"
    range_key       = "GSI4SK"
    projection_type = "ALL"
  }

  # GSI5 — deleted-filter view + cascade restore (DELETED#<entity_type> by deleted_at).
  global_secondary_index {
    name            = "GSI5"
    hash_key        = "GSI5PK"
    range_key       = "GSI5SK"
    projection_type = "ALL"
  }

  server_side_encryption {
    enabled = true
  }

  tags = var.tags
}

# System settings singleton (PK setting_id = "system"). Kept out of the core
# table so it never competes for core GSIs and is cheaply cacheable.
resource "aws_dynamodb_table" "settings" {
  name         = local.settings_table
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "setting_id"

  attribute {
    name = "setting_id"
    type = "S"
  }

  server_side_encryption {
    enabled = true
  }

  tags = var.tags
}
