# Main IAM role outputs
output "wallenstam_app_identity_role_arn" {
  description = "ARN of the Wallenstam app identity role"
  value       = aws_iam_role.wallenstam_app_identity_role.arn
}

output "wallenstam_lambda_role_arn" {
  description = "ARN of the Wallenstam lambda role"
  value       = aws_iam_role.wallenstam_lambda_role.arn
}

# Lambda-specific role outputs
output "signup_lambda_role_arn" {
  description = "ARN of the signup lambda role"
  value       = aws_iam_role.signup_lambda_role.arn
}

output "login_lambda_role_arn" {
  description = "ARN of the login lambda role"
  value       = aws_iam_role.login_lambda_role.arn
}

output "delete_user_lambda_role_arn" {
  description = "ARN of the delete user lambda role"
  value       = aws_iam_role.delete_user_lambda_role.arn
}

output "get_rental_invoices_lambda_role_arn" {
  description = "ARN of the get rental invoices lambda role"
  value       = aws_iam_role.get_rental_invoices_lambda_role.arn
}

output "get_rental_invoice_lambda_role_arn" {
  description = "ARN of the get rental invoice lambda role"
  value       = aws_iam_role.get_rental_invoice_lambda_role.arn
}

output "get_user_profile_lambda_role_arn" {
  description = "ARN of the get user profile lambda role"
  value       = aws_iam_role.get_user_profile_lambda_role.arn
}