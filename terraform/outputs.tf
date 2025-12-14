# Root-level Terraform outputs
# These are consumed by service-specific terraform via data sources

output "route53_zone_id" {
  description = "Route53 hosted zone ID for andreas.services"
  value       = data.aws_route53_zone.main.zone_id
}

output "route53_zone_name" {
  description = "Route53 hosted zone name"
  value       = data.aws_route53_zone.main.name
}

output "route53_name_servers" {
  description = "Name servers for the Route53 zone (from AWS domain registration)"
  value       = data.aws_route53_zone.main.name_servers
}

output "acm_certificate_arn" {
  description = "ARN of the wildcard ACM certificate for *.andreas.services"
  value       = aws_acm_certificate.wildcard.arn
}

output "acm_certificate_domain" {
  description = "Domain name of the ACM certificate"
  value       = aws_acm_certificate.wildcard.domain_name
}
