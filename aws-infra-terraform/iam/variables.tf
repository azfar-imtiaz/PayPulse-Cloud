variable "aws_region" {
  type        = string
  description = "AWS region for this infrastructure"
}

variable "iam_user_group" {
  type        = string
  description = "The IAM user group"
}

variable "iam_user" {
  type        = string
  description = "The IAM user"
}

variable "app_identity_role" {
  type        = string
  description = "The IAM app identity role name"
}

variable "lambda_role" {
  type        = string
  description = "The lambda role name"
}

variable "invoices_bucket_name" {
  type        = string
  description = "The S3 bucket which stores the rental invoices"
}

# DynamoDB table references
variable "users_table_arn" {
  type        = string
  description = "The ARN of the users DynamoDB table"
}

variable "rental_invoices_table_arn" {
  type        = string
  description = "The ARN of the rental invoices DynamoDB table"
}

# Secrets Manager reference
variable "jwt_secret_arn" {
  type        = string
  description = "The ARN of the JWT secret"
}

variable "google_oauth_client_id_secret_arn" {
  type        = string
  description = "The ARN of the Google OAuth client ID secret"
}
