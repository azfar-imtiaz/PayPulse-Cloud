variable "aws_region" {
  type        = string
  description = "AWS region for this infrastructure"
}

variable "python_runtime" {
  type        = string
  description = "The Python runtime used for lambda functions"
}

# Lambda function names
variable "lambda_fetch_rental_invoices" {
  type        = string
  description = "The lambda function for fetching all invoices"
}

variable "lambda_fetch_retail_invoices" {
  type        = string
  description = "The lambda function for fetching retail invoices from Gmail"
}

variable "lambda_fetch_latest_rental_invoice" {
  type        = string
  description = "The lambda function for fetching the latest invoice from the email inbox"
}

variable "lambda_parse_rental_invoice" {
  type        = string
  description = "The lambda function for parsing a rental invoice PDF"
}

variable "lambda_send_rental_invoice_notification" {
  type        = string
  description = "The lambda function for sending a notification once a rental invoice has been parsed and stored in DynamoDB"
}

variable "lambda_signup_user" {
  type        = string
  description = "The lambda function is called when a new user signs up"
}

variable "lambda_login_user" {
  type        = string
  description = "The lambda function is called when an existing user logs in"
}

variable "lambda_delete_user" {
  type        = string
  description = "The lambda function deletes all the data for a user in PayPulse-Cloud"
}

variable "lambda_get_invoices" {
  type        = string
  description = "The lambda function retrieves all parsed invoice data (rental or retail) and returns it"
}

variable "lambda_get_rental_invoice" {
  type        = string
  description = "The lambda function retrieves all parsed details for a given invoice ID from the RentalInvoices table"
}

variable "lambda_get_user_profile" {
  type        = string
  description = "The lambda function retrieves the profile information for the authenticated user"
}

variable "lambda_gmail_store_tokens" {
  type        = string
  description = "The lambda function stores OAuth tokens received from iOS app"
}

variable "lambda_parse_retail_invoice" {
  type        = string
  description = "The lambda function for parsing retail invoice HTML using Gemini API"
}

# Table names
variable "invoices_table" {
  type        = string
  description = "The DynamoDB table containing parsed rental invoices data"
}

# Email configuration
variable "rental_invoice_email" {
  type        = string
  description = "The email address from which we receive rental invoices"
}

variable "rental_invoice_email_subject" {
  type        = string
  description = "The subject of the email from which we receive rental invoices"
}

# S3 bucket names
variable "invoices_bucket_name" {
  type        = string
  description = "The S3 bucket which stores the rental invoices"
}

# External resource references
variable "lambda_bucket_id" {
  type        = string
  description = "The ID of the S3 bucket containing Lambda functions"
}

variable "users_table_name" {
  type        = string
  description = "The name of the users DynamoDB table"
}

variable "rental_invoices_table_name" {
  type        = string
  description = "The name of the rental invoices DynamoDB table"
}

variable "rental_invoices_bucket_arn" {
  type        = string
  description = "The ARN of the rental invoices S3 bucket"
}


variable "jwt_secret_version_secret_string" {
  type        = string
  description = "The JWT secret string"
  sensitive   = true
}

variable "google_oauth_client_id" {
  type        = string
  description = "Google OAuth client ID for Gmail API access"
  sensitive   = true
}

variable "gemini_api_key_secret_string" {
  type        = string
  description = "The Gemini API key for retail invoice parsing"
  sensitive   = true
}


variable "sns_topic_arn" {
  type        = string
  description = "The ARN of the SNS topic for notifications"
}

variable "daily_lambda_trigger_arn" {
  type        = string
  description = "The ARN of the daily lambda trigger event rule"
}

variable "weekly_retail_trigger_arn" {
  type        = string
  description = "The ARN of the weekly retail invoice trigger event rule"
}

# IAM role ARNs from IAM module
variable "wallenstam_lambda_role_arn" {
  type        = string
  description = "The ARN of the main Wallenstam lambda role"
}

variable "signup_lambda_role_arn" {
  type        = string
  description = "The ARN of the signup lambda role"
}

variable "delete_user_lambda_role_arn" {
  type        = string
  description = "The ARN of the delete user lambda role"
}

variable "get_invoices_lambda_role_arn" {
  type        = string
  description = "The ARN of the get invoices lambda role"
}

variable "get_rental_invoice_lambda_role_arn" {
  type        = string
  description = "The ARN of the get rental invoice lambda role"
}

variable "get_user_profile_lambda_role_arn" {
  type        = string
  description = "The ARN of the get user profile lambda role"
}

variable "gmail_store_tokens_lambda_role_arn" {
  type        = string
  description = "The ARN of the gmail store tokens lambda role"
}

variable "fetch_retail_invoices_lambda_role_arn" {
  type        = string
  description = "The ARN of the fetch retail invoices lambda role"
}

variable "parse_retail_invoice_lambda_role_arn" {
  type        = string
  description = "The ARN of the parse retail invoice lambda role"
}

variable "vendor_config_table_name" {
  type        = string
  description = "The name of the VendorConfig DynamoDB table"
}

variable "lambda_delete_retail_invoice" {
  type        = string
  description = "Path to delete_retail_invoice lambda function"
}

variable "delete_retail_invoice_lambda_role_arn" {
  type        = string
  description = "IAM role ARN for delete_retail_invoice lambda"
}

# Retail invoice table names
variable "retail_invoices_table_name" {
  type        = string
  description = "The name of the retail invoices DynamoDB table"
}

variable "food_delivery_invoices_table_name" {
  type        = string
  description = "The name of the food delivery invoices DynamoDB table"
}

variable "clothing_invoices_table_name" {
  type        = string
  description = "The name of the clothing invoices DynamoDB table"
}

variable "technology_invoices_table_name" {
  type        = string
  description = "The name of the technology invoices DynamoDB table"
}

variable "subscription_invoices_table_name" {
  type        = string
  description = "The name of the subscription invoices DynamoDB table"
}

variable "grocery_invoices_table_name" {
  type        = string
  description = "The name of the grocery invoices DynamoDB table"
}

variable "misc_utility_invoices_table_name" {
  type        = string
  description = "The name of the miscellaneous utility invoices DynamoDB table"
}

variable "misc_invoices_table_name" {
  type        = string
  description = "The name of the miscellaneous invoices DynamoDB table"
}

variable "travel_invoices_table_name" {
  type        = string
  description = "The name of the travel invoices DynamoDB table"
}