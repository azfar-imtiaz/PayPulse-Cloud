# Lambda function outputs
output "fetch_invoices_function_name" {
  description = "Name of the fetch invoices lambda function"
  value       = aws_lambda_function.fetch_invoices.function_name
}

output "fetch_invoices_invoke_arn" {
  description = "Invoke ARN of the fetch invoices lambda function"
  value       = aws_lambda_function.fetch_invoices.invoke_arn
}

output "fetch_latest_invoice_function_name" {
  description = "Name of the fetch latest invoice lambda function"
  value       = aws_lambda_function.fetch_latest_invoice.function_name
}

output "fetch_latest_invoice_invoke_arn" {
  description = "Invoke ARN of the fetch latest invoice lambda function"
  value       = aws_lambda_function.fetch_latest_invoice.invoke_arn
}

output "parse_invoice_function_name" {
  description = "Name of the parse invoice lambda function"
  value       = aws_lambda_function.parse_invoice.function_name
}

output "parse_invoice_arn" {
  description = "ARN of the parse invoice lambda function"
  value       = aws_lambda_function.parse_invoice.arn
}

output "send_invoice_notification_function_name" {
  description = "Name of the send invoice notification lambda function"
  value       = aws_lambda_function.send_invoice_notification.function_name
}

output "send_invoice_notification_arn" {
  description = "ARN of the send invoice notification lambda function"
  value       = aws_lambda_function.send_invoice_notification.arn
}

output "signup_user_function_name" {
  description = "Name of the signup user lambda function"
  value       = aws_lambda_function.signup_user.function_name
}

output "signup_user_invoke_arn" {
  description = "Invoke ARN of the signup user lambda function"
  value       = aws_lambda_function.signup_user.invoke_arn
}

output "login_user_function_name" {
  description = "Name of the login user lambda function"
  value       = aws_lambda_function.login_user.function_name
}

output "login_user_invoke_arn" {
  description = "Invoke ARN of the login user lambda function"
  value       = aws_lambda_function.login_user.invoke_arn
}

output "delete_user_function_name" {
  description = "Name of the delete user lambda function"
  value       = aws_lambda_function.delete_user.function_name
}

output "delete_user_invoke_arn" {
  description = "Invoke ARN of the delete user lambda function"
  value       = aws_lambda_function.delete_user.invoke_arn
}

output "get_rental_invoices_function_name" {
  description = "Name of the get rental invoices lambda function"
  value       = aws_lambda_function.get_rental_invoices.function_name
}

output "get_rental_invoices_invoke_arn" {
  description = "Invoke ARN of the get rental invoices lambda function"
  value       = aws_lambda_function.get_rental_invoices.invoke_arn
}

output "get_rental_invoice_function_name" {
  description = "Name of the get rental invoice lambda function"
  value       = aws_lambda_function.get_rental_invoice.function_name
}

output "get_rental_invoice_invoke_arn" {
  description = "Invoke ARN of the get rental invoice lambda function"
  value       = aws_lambda_function.get_rental_invoice.invoke_arn
}

output "get_user_profile_function_name" {
  description = "Name of the get user profile lambda function"
  value       = aws_lambda_function.get_user_profile.function_name
}

output "get_user_profile_invoke_arn" {
  description = "Invoke ARN of the get user profile lambda function"
  value       = aws_lambda_function.get_user_profile.invoke_arn
}

output "gmail_store_tokens_function_name" {
  description = "Name of the Gmail store tokens lambda function"
  value       = aws_lambda_function.gmail_store_tokens.function_name
}

output "gmail_store_tokens_invoke_arn" {
  description = "Invoke ARN of the Gmail store tokens lambda function"
  value       = aws_lambda_function.gmail_store_tokens.invoke_arn
}

# Lambda layers outputs
output "utils_layer_arn" {
  description = "ARN of the utils lambda layer"
  value       = aws_lambda_layer_version.utils_layer.arn
}

output "pyjwt_layer_arn" {
  description = "ARN of the PyJWT lambda layer"
  value       = aws_lambda_layer_version.pyjwt_layer.arn
}

output "bcrypt_layer_arn" {
  description = "ARN of the bcrypt lambda layer"
  value       = data.klayers_package_latest_version.bcrypt.arn
}