# modules/hosting/outputs.tf

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID"
  value       = aws_cloudfront_distribution.app.id
}

output "cloudfront_domain_name" {
  description = "CloudFront distribution domain name"
  value       = aws_cloudfront_distribution.app.domain_name
}

output "certificate_arn" {
  description = "ACM certificate ARN"
  value       = data.aws_acm_certificate.wildcard.arn
}
