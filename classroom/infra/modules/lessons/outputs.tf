output "bucket_id" {
  description = "Name of the lesson content bucket"
  value       = aws_s3_bucket.lessons.id
}

output "bucket_arn" {
  description = "ARN of the lesson content bucket"
  value       = aws_s3_bucket.lessons.arn
}

output "bucket_regional_domain_name" {
  description = "Regional domain name, used as a CloudFront origin"
  value       = aws_s3_bucket.lessons.bucket_regional_domain_name
}
