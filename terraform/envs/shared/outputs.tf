# envs/shared/outputs.tf
#
# VPC, subnet, and DocumentDB outputs have been removed.
# All services now use DynamoDB — no shared networking required.

output "route53_zone_id" {
  description = "Route53 hosted zone ID for andreas.services"
  value       = data.aws_route53_zone.main.zone_id
}

output "route53_name_servers" {
  description = "Name servers for the root domain (configure at your registrar)"
  value       = data.aws_route53_zone.main.name_servers
}

output "acm_certificate_arn" {
  description = "ARN of the *.andreas.services wildcard ACM certificate (us-east-1)"
  value       = aws_acm_certificate.wildcard.arn
}
