// Stripe's webhook lands here, and this file does one thing: enqueue it.
//
// It is the public half of `infra/modules/webhook_relay` — a zip Terraform
// packages straight from this file, no build, no ECR — which is what makes a
// per-machine public endpoint cost seconds per apply. It imports only the SQS
// client the Node Lambda runtime ships. The other half is the backend itself:
// `Consumers/StripeWebhooks/AwsLambdaStripeWebhookConsumer.cs` drains the queue
// — as a Lambda in prod, as a Compose service beside the API in dev — and its
// `Envelope` record is the message shape below. Nothing else reads it.
//
// This handler does NOT verify the signature, deliberately. Verification is
// byte-exact over `<timestamp>.<raw body>` under the endpoint's `whsec_`, so
// this base64s the bytes that arrived rather than re-serialising anything, and
// the consumer — which holds the secret, this function does not — checks them.
// One implementation, in the process that also forwards; a copy here would be a
// second one, in the one file deployed without being run with the rest.
//
// What that costs is an endpoint anyone can push a message into. It is bounded
// rather than ignored: API Gateway throttles the route, the body is capped
// below, and a forged message costs one consumer receive that refuses it.
import { SQSClient, SendMessageCommand } from '@aws-sdk/client-sqs';

// The one header the consumer needs, and the only one carried through. API
// Gateway forwards a great deal that has no business being copied into a queue
// a laptop reads — forwarded IPs, the gateway's own tracing.
const SIGNATURE_HEADER = 'stripe-signature';

// SQS refuses a body over 256 KiB. A Stripe event is a few KiB; a Checkout
// Session with line items and a customer is tens. The cap sits under the SQS
// limit so the refusal happens here, where it is logged, rather than as a
// SendMessage failure with no context.
const MAX_BODY_BYTES = 192 * 1024;

const sqs = new SQSClient({});

export async function handler(event) {
  const raw = Buffer.from(event.body ?? '', event.isBase64Encoded ? 'base64' : 'utf8');
  if (raw.length > MAX_BODY_BYTES) {
    console.log(`webhook body is ${raw.length} bytes; refusing to queue it`);
    return { statusCode: 413, body: JSON.stringify({ error: 'webhook too large' }) };
  }

  const signature = Object.entries(event.headers ?? {}).find(
    ([name]) => name.toLowerCase() === SIGNATURE_HEADER,
  )?.[1];
  if (!signature) {
    // Not from Stripe. Nothing downstream could verify it and nothing should be
    // queued for it.
    return { statusCode: 400, body: JSON.stringify({ error: 'no signature' }) };
  }

  await sqs.send(
    new SendMessageCommand({
      QueueUrl: process.env.HUMBUGG_WEBHOOK_QUEUE_URL,
      MessageBody: JSON.stringify({
        signature,
        // Base64 because the signature is over these exact bytes and a JSON
        // round trip of the decoded string is not guaranteed to reproduce them.
        body_b64: raw.toString('base64'),
        received_at: new Date().toISOString(),
      }),
    }),
  );
  console.log(`queued a webhook (${raw.length} bytes)`);

  // Always 2xx once queued, whatever the body turns out to be. Stripe's only
  // response to anything else is to retry, and a retry delivers the identical
  // body — so a 4xx here would turn one unreadable event into several, and
  // enough of them get the endpoint disabled.
  return { statusCode: 202, body: JSON.stringify({ queued: true }) };
}
