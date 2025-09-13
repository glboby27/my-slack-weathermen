output "update_status_lambda_arn" {
  value = aws_lambda_function.update_status.arn
}
output "daily_planner_lambda_arn" {
  value = aws_lambda_function.daily_planner.arn
}
output "scheduler_target_role_arn" {
  value = aws_iam_role.scheduler_target_role.arn
}
