from __future__ import annotations

from email.message import EmailMessage
from typing import Protocol


class MailTransport(Protocol):
    """Delivery boundary implemented by environment-specific transports."""

    def send(self, message: EmailMessage) -> None: ...
