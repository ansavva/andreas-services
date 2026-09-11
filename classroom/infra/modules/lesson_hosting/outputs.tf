output "distribution_id" {
  description = "CloudFront distribution ID, for cache invalidation"
  value       = aws_cloudfront_distribution.lessons.id
}

output "distribution_arn" {
  description = "Distribution ARN, granted read on the lesson bucket via OAC"
  value       = aws_cloudfront_distribution.lessons.arn
}

output "lesson_base_url" {
  description = "Base URL a lesson link is built from"
  value       = "https://${var.domain_name}"
}
