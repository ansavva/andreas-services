output "base_url" {
  description = <<-EOT
    The origin Replicate is told to call back on — `STUDIO_WEBHOOK_BASE_URL` for
    whatever creates predictions. **Not the studio API's own origin**: in prod
    the two are different gateways, and on a developer's machine they are not
    even the same kind of thing, because the API is Flask on `localhost:8000`
    and this is a real AWS endpoint.

    `services/generate.callback_url` appends `/api/hooks/replicate/<run_id>`.
  EOT
  value       = aws_apigatewayv2_stage.main.invoke_url
}

output "queue_url" {
  description = <<-EOT
    The queue a received callback lands on. Prod's worker is wired to it by an
    event source mapping and never reads this; it is here for the dev
    environment, where `dev-up.sh` exports it as `STUDIO_CALLBACK_QUEUE_URL` and
    a local process long-polls it.
  EOT
  value       = aws_sqs_queue.main.id
}

output "queue_arn" {
  description = "ARN of the callback queue, for a grant declared outside this module."
  value       = aws_sqs_queue.main.arn
}

output "dlq_url" {
  description = <<-EOT
    Where a callback goes after five failed attempts. Worth knowing by name
    rather than by console archaeology: a message here is a generation that was
    paid for and whose output was never stored.
  EOT
  value       = aws_sqs_queue.dlq.id
}

output "receiver_function_name" {
  description = "The public receiver Lambda; the only internet-facing unauthenticated component in studio."
  value       = aws_lambda_function.receiver.function_name
}

output "worker_function_name" {
  description = "The prod queue consumer, or \"\" in an environment that has none."
  value       = local.create_worker ? aws_lambda_function.worker[0].function_name : ""
}
