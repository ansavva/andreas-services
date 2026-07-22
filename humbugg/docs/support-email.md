# Support email (`support@humbugg.com`)

Inbound mail for `humbugg.com` is handled by **Google Workspace**. The Workspace
primary domain is `andreas.services`; `humbugg.com` is configured as a **domain
alias**, so every Workspace user automatically has a matching `@humbugg.com`
address, and additional aliases (like `support@humbugg.com`) can be added per
user in the Admin console.

This path is completely separate from product email: product/transactional mail
still originates from `no-reply@humbugg.com` through the shared Mailer platform
over SES (see [`email-operations.md`](./email-operations.md)). The MX records
only affect *inbound* delivery — SES outbound sending, the `humbugg.com` SES
identity, its DKIM CNAMEs, the `mail.humbugg.com` MAIL FROM subdomain, and
Cognito auth email are all untouched.

> **History**: inbound mail previously flowed through an SES receipt rule +
> forwarder Lambda (`humbugg/infra/modules/support_forwarding`, removed). See
> git history if you ever need the old design.

## How it works

```
sender ──▶ MX humbugg.com (1 smtp.google.com) ──▶ Google Workspace
                                                      │
                                          alias: support@humbugg.com
                                                      ▼
                                          Workspace user mailbox
```

- **Receiving**: Google's MX handles all `@humbugg.com` mail. `support@` is an
  alternate email (alias) on the owner's Workspace account — no forwarding
  Lambda, no secret destination address.
- **Replying**: in Gmail, "Send mail as" with the `support@humbugg.com` alias
  (Settings → Accounts → Send mail as → *Treat as alias*, via Google's own
  servers — no SMTP credentials). Replies go out authenticated by Google
  (SPF `_spf.google.com` + DKIM `google._domainkey.humbugg.com`).

## DNS (Terraform-managed)

All records live in `humbugg/infra/modules/email` (zone `humbugg.com`):

| Record | Type | Value | Purpose |
|---|---|---|---|
| `humbugg.com` | MX | `1 smtp.google.com` | Google Workspace inbound |
| `humbugg.com` | TXT | `v=spf1 include:_spf.google.com ~all` (+ any `google-site-verification=` strings) | SPF for Gmail-originated mail from `@humbugg.com` |
| `google._domainkey.humbugg.com` | TXT | `v=DKIM1; k=rsa; p=...` (var `google_dkim_txt_value`) | Google DKIM signing |
| `mail.humbugg.com` | MX + TXT | SES feedback + `include:amazonses.com` | SES MAIL FROM (outbound, unchanged) |
| `_dmarc.humbugg.com` | TXT | `v=DMARC1; p=none; adkim=r; aspf=r; pct=100` | DMARC (both senders align) |

Notes:

- The apex SPF deliberately does **not** include `amazonses.com`: SES outbound
  uses the custom MAIL FROM `mail.humbugg.com`, which carries its own SPF, and
  relaxed DMARC alignment (`aspf=r`) keeps it aligned with `humbugg.com`.
- Route53 allows only one TXT record set per name, so any
  `google-site-verification=` strings must ride in the managed apex TXT record
  (`apex_txt_additional_records` variable) — never delete them; Google
  re-checks domain verification periodically.
- The Google DKIM value is a public key generated in the Admin console
  (Apps → Google Workspace → Gmail → Authenticate email) and passed via the
  `google_dkim_txt_value` variable. After the TXT is live, click **Start
  authentication** in the Admin console.

## Verifying

1. `dig +short MX humbugg.com` → `1 smtp.google.com.`
2. `dig +short TXT humbugg.com` → SPF (+ site-verification) strings.
3. `dig +short TXT google._domainkey.humbugg.com` → the DKIM key.
4. From an external (non-Google) address, email `support@humbugg.com` — it
   should land in the Workspace mailbox.
5. Reply from Gmail as `support@humbugg.com` to an external mailbox and check
   the received headers: `spf=pass`, `dkim=pass header.d=humbugg.com`,
   `dmarc=pass`.
6. Outbound SES mail is unaffected — the `email-feedback-smoke-test` job in
   `humbugg-prod.yaml` still proves delivery from `no-reply@humbugg.com`.
