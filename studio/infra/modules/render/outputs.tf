output "queue_url" {
  description = <<-EOT
    The queue a render job is enqueued onto — `STUDIO_RENDER_QUEUE_URL` on the API
    Lambda, and on `dev-up.sh`'s local consumer.

    **Read by both environments, unlike the callback queue's**, which prod's
    worker never sees because an event source mapping wires it. The API is what
    enqueues here, so it needs the URL wherever it runs.
  EOT
  value       = aws_sqs_queue.main.id
}

output "queue_arn" {
  description = "ARN of the render queue, for a grant declared outside this module."
  value       = aws_sqs_queue.main.arn
}

output "dlq_url" {
  description = <<-EOT
    Where a render goes after five failed attempts. A message here means a
    `RENDER#` row is stuck at `running` and whoever submitted it is still polling
    — nothing perishable, unlike the callback DLQ, but somebody is waiting.
  EOT
  value       = aws_sqs_queue.dlq.id
}

output "ecr_repository_url" {
  description = "ECR repository the deploy workflow pushes the render image to, or \"\"."
  value       = var.create_ecr ? aws_ecr_repository.render[0].repository_url : ""
}

output "worker_function_name" {
  description = "The prod render worker, or \"\" in an environment that has none."
  value       = local.create_worker ? aws_lambda_function.worker[0].function_name : ""
}
