output "topic_arn" {
  description = "SNS topic every Humbugg production alarm publishes to"
  value       = aws_sns_topic.alerts.arn
}

output "topic_name" {
  description = "SNS topic name"
  value       = aws_sns_topic.alerts.name
}
