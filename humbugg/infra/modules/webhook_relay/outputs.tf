output "endpoint_url" {
  description = <<-EOT
    The URL registered with Stripe as this environment's webhook endpoint — in
    dev `dev-aws-setup.sh` posts it to `/v1/webhook_endpoints`, in prod a
    person does (docs/stripe-setup.md). Not the backend's URL: Stripe reaches
    this, and the consumer reaches the backend.
  EOT
  value       = "${trimsuffix(aws_apigatewayv2_stage.main.invoke_url, "/")}/stripe/webhook"
}

output "queue_url" {
  description = <<-EOT
    The queue a received webhook lands on. Prod's consumer Lambda is wired to
    it by an event source mapping and never reads this; `dev-aws-setup.sh`
    writes it into dev.env as `HUMBUGG_WEBHOOK_QUEUE_URL` for the consumer
    `dev-up.sh` starts.
  EOT
  value       = aws_sqs_queue.main.id
}

output "dlq_url" {
  description = "Where a webhook goes after ten failed forwards. Read it when a purchase will not complete."
  value       = aws_sqs_queue.dlq.id
}

output "receiver_function_name" {
  description = "The public receiver Lambda; the only internet-facing unauthenticated component that writes."
  value       = aws_lambda_function.receiver.function_name
}

output "consumer_function_name" {
  description = "The prod queue consumer, or \"\" in an environment whose consumer is a laptop."
  value       = var.create_consumer ? aws_lambda_function.consumer[0].function_name : ""
}
