output "signup_api_url" {
  description = "Invoke URL for the signup API endpoint"
  value       = aws_apigatewayv2_api.signup_api.api_endpoint
}