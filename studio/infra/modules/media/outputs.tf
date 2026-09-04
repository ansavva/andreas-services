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
