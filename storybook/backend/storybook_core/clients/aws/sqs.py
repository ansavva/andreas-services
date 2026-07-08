import json
import boto3


class SqsClient:
    def __init__(self, region: str):
        self._client = boto3.client("sqs", region_name=region)

    def receive_messages(self, queue_url: str, max_messages: int, wait_seconds: int):
        response = self._client.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=max_messages,
            WaitTimeSeconds=wait_seconds,
        )
        return response.get("Messages", [])

    def delete_message(self, queue_url: str, receipt_handle: str) -> None:
        self._client.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)

    def send_message(self, queue_url: str, message_body: dict) -> None:
        self._client.send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps(message_body),
        )
