output "api_function_name" {
  description = "Name of the API Lambda; the deploy workflow updates its code and env"
  value       = aws_lambda_function.api.function_name
}

output "api_invoke_arn" {
  description = "Invoke ARN wired into the API Gateway integration"
  value       = aws_lambda_function.api.invoke_arn
}

output "api_role_arn" {
  description = "ARN of the API Lambda's execution role"
  value       = aws_iam_role.api.arn
}

output "ecr_repository_url" {
  description = "ECR repository the deploy workflow pushes the API image to"
  value       = var.create_ecr ? aws_ecr_repository.api[0].repository_url : ""
}

output "api_role_name" {
  description = <<-EOT
    Name of the API Lambda's execution role. **The callback worker runs under
    this same role**: it does exactly what the API does — the media bucket, the
    catalog, the provider token — so a role of its own would be a hand-kept copy
    of these policies that eventually drifts. `modules/callbacks` attaches one
    extra inline policy to it for the queue.
  EOT
  value       = aws_iam_role.api.name
}

# THE TWO POLICY DOCUMENTS, SO A SECOND ROLE CAN BE A SECOND ROLE.
#
# `modules/callbacks` takes the API's role whole and argues, correctly, that its
# worker does exactly what the API does — so a role of its own would be a
# hand-kept copy of a hundred lines of carefully reasoned policy that eventually
# drifts.
#
# **The render worker is the case where that argument runs out.** It reads and
# writes the media bucket and the catalog like everything else here, and it never
# touches Replicate: it stitches files that are already in the library. Handing
# it the API's role would hand it `ssm:GetParameter` and `kms:Decrypt` on the
# provider token — the ability to spend money — for a function that has no code
# path to spend it with.
#
# Exporting the documents rather than the role gets both properties at once: one
# definition of what access to the library means, and a role per function scoped
# to what that function does. `modules/render` attaches these to its own role and
# adds logs and its queue, and nothing about the provider token comes with them.
output "media_access_policy" {
  description = "The media-bucket policy document, for a second execution role that needs the same access."
  value       = data.aws_iam_policy_document.media_access.json
}

output "catalog_access_policy" {
  description = "The catalog-table policy document, for a second execution role that needs the same access."
  value       = data.aws_iam_policy_document.catalog_access.json
}
