variable "aws_region" {
  type        = string
  description = "AWS region for this infrastructure"
  default     = "eu-west-1"
}

# IAM user group

variable "iam_user_group" {
  type        = string
  description = "The IAM user group"
  default     = "Wallenstam"
}

# IAM user

variable "iam_user" {
  type        = string
  description = "The IAM user"
  default     = "WallenstamTenant"
}

# IAM roles

variable "app_identity_role" {
  type        = string
  description = "The IAM app identity role name"
  default     = "WallenstamAppIdentityRole"
}

variable "lambda_role" {
  type        = string
  description = "The lambda role name"
  default     = "Wallenstam-Lambda-Role"
}

# S3 buckets

variable "invoices_bucket_name" {
  type        = string
  description = "The S3 bucket which stores the rental invoices"
  default     = "rental-invoices-bucket"
}

variable "path_to_invoices" {
  type        = string
  description = "The path to the rental invoices on the S3 bucket"
  default     = "rental-invoices/"
}

variable "lambda_functions_bucket_name" {
  type        = string
  description = "The S3 bucket which contains zipped files of the lambda functions"
  default     = "wallenstam-lambda-bucket"
}

# DynamoDB

variable "invoices_table" {
  type        = string
  description = "The DynamoDB table containing parsed rental invoices data"
  default     = "RentalInvoices"
}

variable "invoices_table_hash_key" {
  type        = string
  description = "The hash key of the rental invoices DB table"
  default     = "UserID"
}

variable "invoices_table_range_key" {
  type        = string
  description = "The hash key of the rental invoices DB table"
  default     = "InvoiceID"
}

variable "invoices_table_due_date_year" {
  type        = string
  description = "Column name for due date year"
  default     = "due_date_year"
}

variable "invoices_table_due_date_month" {
  type        = string
  description = "Column name for due date month"
  default     = "due_date_month"
}

variable "users_table" {
  type        = string
  description = "The DynamoDB table containing user information"
  default     = "Users"
}

variable "users_table_hash_key" {
  type        = string
  description = "The hash key of the users DB table"
  default     = "UserID"
}

# SNS

variable "rental_invoice_notification_topic" {
  type        = string
  description = "The notification topic for new rental invoices"
  default     = "NewInvoiceNotificationTopic"
}

variable "rental_invoice_notification_display_name" {
  type        = string
  description = "The display name for a new rental invoice notification"
  default     = "PayPulse"
}

# Secrets Manager

variable "gmail_secret_credentials" {
  description = "JSON secret string for Gmail access credentials."
  type        = string
  sensitive   = true
}

# EventBridge

variable "daily_lambda_trigger" {
  type        = string
  description = "The name of the daily lambda function trigger to check for a new rental invoice"
  default     = "DailyLambdaTrigger"
}

variable "daily_lambda_trigger_schedule" {
  type        = string
  description = "The schedule expression of the daily lambda function trigger cron job"
  default     = "cron(30 8 ? * MON-FRI *)"  # This is 8:30 AM UTC
}

# Lambda

variable "python_runtime" {
  type        = string
  description = "The Python runtime used for lambda functions"
  default     = "python3.12"
}

variable "lambda_fetch_rental_invoices" {
  type        = string
  description = "The lambda function for fetching all invoices"
  default     = "fetch_invoices"
}

variable "lambda_fetch_latest_rental_invoice" {
  type        = string
  description = "The lambda function for fetching the latest invoice from the email inbox"
  default     = "fetch_latest_invoice"
}

variable "lambda_parse_rental_invoice" {
  type        = string
  description = "The lambda function for parsing a rental invoice PDF"
  default     = "parse_invoice"
}

variable "lambda_send_rental_invoice_notification" {
  type        = string
  description = "The lambda function for sending a notification once a rental invoice has been parsed and stored in DynamoDB"
  default     = "send_invoice_notification"
}

variable "lambda_signup_user" {
  type        = string
  description = "The lambda function called when a new user signs up"
  default     = "signup_user"
}

variable "lambda_login_user" {
  type        = string
  description = "The lambda function called when an existing user logs in"
  default     = "login_user"
}

variable "rental_invoice_email" {
  type        = string
  description = "The email address from which we receive rental invoices"
  default     = "kundservice@wallenstam.se"
}

variable "rental_invoice_email_subject" {
  type        = string
  description = "The subject of the email from which we receive rental invoices"
  default     = "hyresavi"
}

# Cognito

variable "identity_pool_name" {
  type        = string
  description = "The Identity Pool Name for Cognito"
  default     = "WallenstamAppIdentityPool"
}