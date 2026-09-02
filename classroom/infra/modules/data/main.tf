locals {
  pages_table = "${var.project}-${var.environment}-pages"
}

# One table holds every page, keyed by its owning teacher so a teacher's list is
# a single query. GSI1 indexes the public slug so an anonymous student read is
# also a single query rather than a scan.
#
# The GSI1 attributes are written only while a page is published — the write
# path REMOVEs them on withdrawal — so an unpublished page falls out of the
# public lookup with no filter expression. See backend/classroom_core/
# repositories/store.py.
resource "aws_dynamodb_table" "pages" {
  name         = local.pages_table
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

  # GSI1 — public slug lookup (SLUG#<slug>), sparse over published pages only.
  global_secondary_index {
    name            = "GSI1"
    hash_key        = "GSI1PK"
    range_key       = "GSI1SK"
    projection_type = "ALL"
  }

  # A teacher's pages are the only copy of work they may have spent an evening
  # on, and this table is small enough that continuous backups cost almost
  # nothing.
  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true
  }

  tags = var.tags
}
