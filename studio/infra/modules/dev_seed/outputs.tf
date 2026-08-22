output "bucket_name" {
  description = "The seed bucket's name — what STUDIO_DEV_SEED_BUCKET overrides"
  value       = aws_s3_bucket.seed.id
}

output "bucket_arn" {
  description = "The seed bucket's ARN, for a read-only policy when one is needed"
  value       = aws_s3_bucket.seed.arn
}
