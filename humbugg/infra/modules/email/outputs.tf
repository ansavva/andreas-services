output "identity_arn" {
  description = "SES identity ARN authorized to send Humbugg mail"
  value       = aws_ses_domain_identity.domain.arn
}

output "from_address" {
  description = "Transactional From address"
  value       = local.from_address
}

output "mail_from_domain" {
  description = "Custom SES MAIL FROM domain"
  value       = local.mail_from_domain
}
