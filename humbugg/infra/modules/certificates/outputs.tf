# The validation resource's ARN, not the raw certificate's: consuming it makes every
# dependent wait until ACM has actually issued the certificate.
output "certificate_arn" {
  description = "ARN of the validated certificate"
  value       = aws_acm_certificate_validation.main.certificate_arn
}
