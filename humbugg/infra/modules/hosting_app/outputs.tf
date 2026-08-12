output "cloudfront_distribution_id" {
  description = "Product app CloudFront distribution ID"
  value       = aws_cloudfront_distribution.app.id
}

output "cloudfront_domain_name" {
  description = "Product app CloudFront distribution domain name"
  value       = aws_cloudfront_distribution.app.domain_name
}
