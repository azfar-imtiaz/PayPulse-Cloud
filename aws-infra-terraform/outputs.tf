output "paypulse_api_url" {
  description = "Invoke URL for the PayPulse API"
  value       = aws_apigatewayv2_api.paypulse_api.api_endpoint
}