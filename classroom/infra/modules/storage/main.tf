resource "aws_s3_bucket" "main" {
  bucket = var.bucket_name

  # The frontend bucket holds only build output, so it is regenerable and takes
  # force_destroy at creation — retrofitting the flag during a rename is too
  # late, because Terraform reads it from prior state (see root CLAUDE.md).
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
