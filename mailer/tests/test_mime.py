from mailer.shared.config import ServiceConfig
from mailer.shared.mime import AttachmentContent, build_message
from mailer.shared.models import MessageRequest


def service():
    return ServiceConfig(
        service_id="humbugg",
        sender_name="Humbugg",
        sender_address="no-reply@humbugg.com",
        allowed_categories=frozenset({"invitation"}),
        allowed_message_classes=frozenset({"exchange"}),
    )


def request(attachments=None):
    return MessageRequest.from_dict(
        {
            "schema_version": 1,
            "application_message_id": "hmb_invitation_123",
            "category": "invitation",
            "message_class": "exchange",
            "to_address": "recipient@example.com",
            "subject": "Invitation",
            "html_body": "<p>Hello</p>",
            "text_body": "Hello",
            "attachments": attachments or [],
        },
        service(),
    )


def test_message_contains_text_html_and_privacy_safe_diagnostics():
    value = build_message(service(), request(), [])

    assert value["From"] == "Humbugg <no-reply@humbugg.com>"
    assert value["X-Mailer-Service-Id"] == "humbugg"
    assert value.get_body(preferencelist=("html",)).get_content().strip() == "<p>Hello</p>"
    assert value.get_body(preferencelist=("plain",)).get_content().strip() == "Hello"


def test_message_contains_attachment():
    value = build_message(
        service(),
        request(
            [
                {
                    "attachment_id": "att_123",
                    "disposition": "attachment",
                    "content_id": None,
                }
            ]
        ),
        [
            AttachmentContent(
                attachment_id="att_123",
                file_name="guide.pdf",
                content_type="application/pdf",
                disposition="attachment",
                content_id=None,
                data=b"pdf",
            )
        ],
    )

    attachment = next(value.iter_attachments())
    assert attachment.get_filename() == "guide.pdf"
    assert attachment.get_payload(decode=True) == b"pdf"
