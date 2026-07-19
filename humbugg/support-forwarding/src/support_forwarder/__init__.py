"""Inbound support-mail forwarder for support@humbugg.com.

This package holds the AWS Lambda that SES invokes for mail received on the
support address. It parses the raw MIME safely, builds a brand-new forwarded
message (never relaying untrusted headers), and delivers it from
no-reply@humbugg.com to a private destination supplied through a secret.
"""

from .handler import lambda_handler

__all__ = ["lambda_handler"]
