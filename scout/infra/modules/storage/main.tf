resource "aws_s3_bucket" "main" {
  bucket = var.bucket_name

  # Ephemeral per-PR buckets must be destroyable even when they still contain
  # objects (the processor writes artifacts/images during the preview's life);
  # otherwise teardown's `terraform destroy` fails with BucketNotEmpty (409).
  # Defaults to false so persistent buckets are safe.
  force_destroy = var.force_destroy

  tags = var.tags
}

resource "aws_s3_bucket_public_access_block" "main" {
  bucket = aws_s3_bucket.main.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
