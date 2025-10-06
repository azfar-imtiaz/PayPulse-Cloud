output "paypulse_api_url" {
  description = "Invoke URL for the PayPulse API"
  value       = aws_apigatewayv2_api.paypulse_api.api_endpoint
}

# Retail Invoices Tables Outputs

output "retail_invoices_table_name" {
  value       = aws_dynamodb_table.retail_invoices.name
  description = "RetailInvoices table name"
}

output "retail_invoices_table_arn" {
  value       = aws_dynamodb_table.retail_invoices.arn
  description = "RetailInvoices table ARN"
}

output "retail_invoices_stream_arn" {
  value       = aws_dynamodb_table.retail_invoices.stream_arn
  description = "RetailInvoices table stream ARN"
}

output "food_delivery_invoices_table_name" {
  value       = aws_dynamodb_table.food_delivery_invoices.name
  description = "FoodDeliveryInvoices table name"
}

output "food_delivery_invoices_table_arn" {
  value       = aws_dynamodb_table.food_delivery_invoices.arn
  description = "FoodDeliveryInvoices table ARN"
}

output "clothing_invoices_table_name" {
  value       = aws_dynamodb_table.clothing_invoices.name
  description = "ClothingInvoices table name"
}

output "clothing_invoices_table_arn" {
  value       = aws_dynamodb_table.clothing_invoices.arn
  description = "ClothingInvoices table ARN"
}

output "technology_invoices_table_name" {
  value       = aws_dynamodb_table.technology_invoices.name
  description = "TechnologyInvoices table name"
}

output "technology_invoices_table_arn" {
  value       = aws_dynamodb_table.technology_invoices.arn
  description = "TechnologyInvoices table ARN"
}

output "subscription_invoices_table_name" {
  value       = aws_dynamodb_table.subscription_invoices.name
  description = "SubscriptionInvoices table name"
}

output "subscription_invoices_table_arn" {
  value       = aws_dynamodb_table.subscription_invoices.arn
  description = "SubscriptionInvoices table ARN"
}

output "grocery_invoices_table_name" {
  value       = aws_dynamodb_table.grocery_invoices.name
  description = "GroceryInvoices table name"
}

output "grocery_invoices_table_arn" {
  value       = aws_dynamodb_table.grocery_invoices.arn
  description = "GroceryInvoices table ARN"
}

output "misc_utility_invoices_table_name" {
  value       = aws_dynamodb_table.misc_utility_invoices.name
  description = "MiscellaneousUtilityInvoices table name"
}

output "misc_utility_invoices_table_arn" {
  value       = aws_dynamodb_table.misc_utility_invoices.arn
  description = "MiscellaneousUtilityInvoices table ARN"
}

output "misc_invoices_table_name" {
  value       = aws_dynamodb_table.misc_invoices.name
  description = "MiscellaneousInvoices table name"
}

output "misc_invoices_table_arn" {
  value       = aws_dynamodb_table.misc_invoices.arn
  description = "MiscellaneousInvoices table ARN"
}