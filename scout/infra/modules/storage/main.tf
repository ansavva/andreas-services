resource "aws_s3_bucket" "main" {
  bucket = var.bucket_name

  # Defaults to false: `terraform destroy` on a bucket holding objects fails
  # with BucketNotEmpty (409), which is the safe outcome for a bucket holding
  # real artifacts.
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
