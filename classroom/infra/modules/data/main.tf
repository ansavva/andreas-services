locals {
  pages_table = "${var.project}-${var.environment}-pages"
}

# One table holds every page, keyed by its owning teacher so a teacher's list is
# a single query.
#
# **Metadata only.** A page's content is a directory of files in S3 — see
# modules/lessons — and this table holds what a directory cannot: the title, the
# publication state, the timestamps and the file count.
#
# There is no secondary index. GSI1 used to map a public slug to a page so an
# anonymous student read was a single query; students now open a lesson's files
# straight from CloudFront and never reach the API, so the index had no queries
# left. See backend/classroom_core/repositories/store.py.
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
