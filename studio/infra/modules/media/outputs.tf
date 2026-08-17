output "bucket_name" {
  description = "Name (id) of the media bucket."
  value       = aws_s3_bucket.this.id
}

output "bucket_arn" {
  description = "ARN of the media bucket."
  value       = aws_s3_bucket.this.arn
}

output "bucket_domain_name" {
  description = "Regional domain name of the media bucket."
  value       = aws_s3_bucket.this.bucket_regional_domain_name
}

output "key_prefix" {
  description = "Key prefix the tree lives under (empty = the bucket root)."
  value       = var.key_prefix
}

output "media_uri" {
  description = "Convenience s3:// URI for the tree root."
  value       = "s3://${aws_s3_bucket.this.id}/${var.key_prefix}"
}
