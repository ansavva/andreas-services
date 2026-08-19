terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source = "hashicorp/aws"
      # Pinned to the major `envs/prod` pins, as `modules/media` is. It also
      # keeps a standalone `terraform validate` in this directory honest: under
      # provider 6.x, `hash_key`/`range_key` warn as deprecated in favour of
      # `key_schema`, which does not exist in 5.x. Without the constraint the
      # module validates against a provider prod never uses.
      version = "~> 5.0"
    }
  }
}

# THE CATALOG — the library itself.
#
# Every other store in studio can be rebuilt: the ECR image comes from git, the
# SPA bundle from a build. This table cannot, and neither can the bucket it
# describes — but the two fail differently, and that difference is the point of
# this module.
#
# `modules/media` holds the bytes and nothing lists them. Identity, name, parent
# and owner are rows here; an S3 key is an opaque `blob_key` nothing derives or
# parses. So a lost row is a lost file even though every byte of it survives,
# and no amount of S3 versioning reaches it. Rename, move, share and transfer are
# row writes that touch zero objects — the same property, seen from the other
# side.
#
# The table is single-table by necessity rather than fashion. A node is stored
# twice — `NODE#<parent>` / `NAME#<name>` for list-by-parent and unique names,
# `NODE#<id>` / `META` for the attributes — so every write is a
# `TransactWriteItems` and a rename is three operations. That is the price of
# getting both access patterns from one consistency boundary. The full item
# table lives in the epic, not here; Terraform only ever sees the keys.
#
# `PAY_PER_REQUEST` because the load is one person browsing a library of a few
# thousand rows. There is no throughput to forecast and no idle capacity worth
# paying for.
resource "aws_dynamodb_table" "catalog" {
  name         = var.table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"

  # Only key attributes appear here — the table's and the three indexes'. The
  # rest of a node (`name`, `kind`, `blob_key`, `size`, `path`'s siblings) is
  # schemaless and deliberately invisible to Terraform; declaring a non-key
  # attribute is an error, not a no-op.
  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  attribute {
    name = "lib"
    type = "S"
  }

  attribute {
    name = "path"
    type = "S"
  }

  attribute {
    name = "created_at"
    type = "S"
  }

  # Reverse lookup. Membership rows are `USER#<sub>` / `LIB#<lib>`, which answers
  # "which libraries can this caller see" from the base table; this index answers
  # the other direction — "who is in library X" — without a second row per
  # membership to keep in step.
  global_secondary_index {
    name            = "by-sk"
    hash_key        = "sk"
    range_key       = "pk"
    projection_type = "ALL"
  }

  # Recursive subtree listing. `path` is materialised ancestor ids
  # (`/node-a/node-b/`), so a `begins_with` on it returns a whole subtree in one
  # query. `parent_id` stays authoritative and this is a derived index — a move
  # rewrites `path` on every descendant, bounded and batched, and touches no
  # bytes.
  global_secondary_index {
    name            = "by-path"
    hash_key        = "lib"
    range_key       = "path"
    projection_type = "ALL"
  }

  # Newest/oldest across a library, genuinely paginated. This is what retires the
  # reel's current shape: today it lists up to 20,000 S3 objects and breaks ties
  # on the key, because `LastModified` has one-second resolution and a run writes
  # its whole output inside one second. `created_at` is a real microsecond
  # timestamp, so ties stop being the common case.
  global_secondary_index {
    name            = "by-recent"
    hash_key        = "lib"
    range_key       = "created_at"
    projection_type = "ALL"
  }

  # `enabled = true` is not the difference between encrypted and not — DynamoDB
  # is always encrypted at rest. It selects the AWS-managed `aws/dynamodb` key
  # over the default AWS-owned one, which is what makes the encryption auditable
  # in KMS. No `kms_key_arn`: a customer-managed key would be one more thing that
  # can be revoked or deleted out from under the table, and it buys nothing here.
  server_side_encryption {
    enabled = true
  }

  # Continuous backups, 35 days, restorable to any second.
  #
  # The variable defaults to ON, and that is the deliberate half. The two risks
  # are not symmetric: forgetting to enable it costs the library, while enabling
  # it needlessly costs cents a month on a table holding metadata for a few
  # thousand files. More to the point, PITR is the ONLY recovery this data has.
  # The bucket's protection is versioning plus a role with no
  # `s3:DeleteObjectVersion`, so every delete studio can perform there is a
  # tombstone it can be reached back past. Nothing equivalent exists for a row —
  # a bad transaction during a move or a transfer, which rewrites `path` or `lib`
  # across an entire subtree, overwrites in place and leaves nothing behind.
  #
  # An environment that genuinely does not want it — a throwaway dev table whose
  # contents are fixtures — has to say so, which is the right way round.
  point_in_time_recovery {
    enabled = var.point_in_time_recovery_enabled
  }

  tags = var.tags
}
