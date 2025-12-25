# envs/shared/outputs.tf

output "route53_zone_id" {
  description = "Route53 hosted zone ID"
  value       = data.aws_route53_zone.main.zone_id
}

output "route53_name_servers" {
  description = "Name servers for the root domain"
  value       = data.aws_route53_zone.main.name_servers
}

output "acm_certificate_arn" {
  description = "ARN of the wildcard ACM certificate"
  value       = aws_acm_certificate.wildcard.arn
}

output "shared_vpc_id" {
  description = "Shared VPC ID for all apps"
  value       = module.shared_networking.vpc_id
}

output "shared_private_subnet_ids" {
  description = "Private subnet IDs for app workloads"
  value       = module.shared_networking.private_subnet_ids
}

output "shared_docdb_cluster_endpoint" {
  description = "Shared DocumentDB cluster endpoint"
  value       = module.shared_database.cluster_endpoint
}

output "shared_docdb_reader_endpoint" {
  description = "Shared DocumentDB reader endpoint"
  value       = module.shared_database.cluster_reader_endpoint
}

output "shared_docdb_connection_string" {
  description = "Shared DocumentDB connection string (without credentials)"
  value       = module.shared_database.connection_string
  sensitive   = true
}

output "shared_docdb_security_group_id" {
  description = "Security group protecting the shared DocumentDB cluster"
  value       = module.shared_database.security_group_id
}
