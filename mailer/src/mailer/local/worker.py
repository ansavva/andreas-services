from __future__ import annotations

import logging
import queue
import threading

from mailer.local.state import LocalDelivery
from mailer.shared.mime import build_message
from mailer.shared.ports import MailTransport

logger = logging.getLogger("mailer.local")


class LocalDeliveryWorker:
    """Drains the ephemeral local queue into the configured local transport."""

    def __init__(
        self,
        deliveries: queue.Queue[LocalDelivery],
        transport: MailTransport,
    ) -> None:
        self.deliveries = deliveries
        self.transport = transport

    def start(self) -> None:
        threading.Thread(
            target=self._run,
            name="mailer-local-delivery",
            daemon=True,
        ).start()

    def _run(self) -> None:
        while True:
            delivery = self.deliveries.get()
            try:
                message = build_message(
                    delivery.service,
                    delivery.request,
                    delivery.attachments,
                )
                self.transport.send(message)
                logger.info(
                    "local email captured service_id=%s application_message_id=%s category=%s",
                    delivery.service.service_id,
                    delivery.request.application_message_id,
                    delivery.request.category,
                )
            except Exception:
                logger.exception(
                    "local email capture failed service_id=%s application_message_id=%s",
                    delivery.service.service_id,
                    delivery.request.application_message_id,
                )
            finally:
                self.deliveries.task_done()
