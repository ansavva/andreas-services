resource "aws_ses_domain_identity" "domain" {
  domain = var.domain_name
}

resource "aws_route53_record" "identity_verification" {
  zone_id = var.route53_zone_id
  name    = "_amazonses.${var.domain_name}"
  type    = "TXT"
  ttl     = 300
  records = [aws_ses_domain_identity.domain.verification_token]
}

resource "aws_ses_domain_identity_verification" "domain" {
  domain = aws_ses_domain_identity.domain.id

  depends_on = [aws_route53_record.identity_verification]
}

resource "aws_ses_domain_dkim" "domain" {
  domain = aws_ses_domain_identity.domain.domain
}

resource "aws_route53_record" "dkim" {
  count = 3

  zone_id = var.route53_zone_id
  name    = "${aws_ses_domain_dkim.domain.dkim_tokens[count.index]}._domainkey.${var.domain_name}"
  type    = "CNAME"
  ttl     = 300
  records = ["${aws_ses_domain_dkim.domain.dkim_tokens[count.index]}.dkim.amazonses.com"]
}

resource "aws_ses_domain_mail_from" "domain" {
  domain                 = aws_ses_domain_identity.domain.domain
  mail_from_domain       = local.mail_from_domain
  behavior_on_mx_failure = "RejectMessage"

  depends_on = [aws_ses_domain_identity_verification.domain]
}

resource "aws_route53_record" "mail_from_mx" {
  zone_id = var.route53_zone_id
  name    = local.mail_from_domain
  type    = "MX"
  ttl     = 300
  records = ["10 feedback-smtp.${var.aws_region}.amazonses.com"]
}

resource "aws_route53_record" "mail_from_spf" {
  zone_id = var.route53_zone_id
  name    = local.mail_from_domain
  type    = "TXT"
  ttl     = 300
  records = ["v=spf1 include:amazonses.com -all"]
}

# --------------------------------------------------------------------------- #
# Inbound mail is handled by Google Workspace (humbugg.com is a domain alias
# of the andreas.services Workspace). Outbound app mail stays on SES via the
# custom MAIL FROM subdomain above — the apex MX/SPF below never affect it.
# --------------------------------------------------------------------------- #
resource "aws_route53_record" "apex_mx" {
  zone_id         = var.route53_zone_id
  name            = var.domain_name
  type            = "MX"
  ttl             = 300
  allow_overwrite = true
  records         = ["1 smtp.google.com"]
}

resource "aws_route53_record" "apex_spf" {
  zone_id         = var.route53_zone_id
  name            = var.domain_name
  type            = "TXT"
  ttl             = 300
  allow_overwrite = true
  records         = concat(["v=spf1 include:_spf.google.com ~all"], var.apex_txt_additional_records)
}

# Google signs as humbugg.com once DKIM is generated in the Admin console.
# A 2048-bit key exceeds Route53's 255-char TXT string limit, so the value is
# split into embedded quoted chunks (the provider's multi-string convention).
resource "aws_route53_record" "google_dkim" {
  count   = var.google_dkim_txt_value != "" ? 1 : 0
  zone_id = var.route53_zone_id
  name    = "google._domainkey.${var.domain_name}"
  type    = "TXT"
  ttl     = 300
  records = [join("\"\"", [for i in range(0, ceil(length(var.google_dkim_txt_value) / 255)) : substr(var.google_dkim_txt_value, i * 255, 255)])]
}

resource "aws_route53_record" "dmarc" {
  zone_id = var.route53_zone_id
  name    = "_dmarc.${var.domain_name}"
  type    = "TXT"
  ttl     = 300
  records = ["v=DMARC1; p=none; adkim=r; aspf=r; pct=100"]
}

locals {
  mail_from_domain = "mail.${var.domain_name}"
  from_address     = "no-reply@${var.domain_name}"
}
