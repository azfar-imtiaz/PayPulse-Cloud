terraform {
	required_providers {
		klayers = {
			source  = "ldcorentin/klayer"
			version = "~> 1.0.0"
		}
		aws = {
			source  = "hashicorp/aws"
			version = "~> 5.0"
		}
	}

	required_version = ">=1.5.0"
}

provider "aws" {
	region = var.aws_region
}

# IAM module
module "iam" {
  source = "./iam"
  
  # Pass required variables
  aws_region              = var.aws_region
  iam_user_group          = var.iam_user_group
  iam_user                = var.iam_user
  app_identity_role       = var.app_identity_role
  lambda_role             = var.lambda_role
  invoices_bucket_name    = var.invoices_bucket_name
  
  # Pass resource references
  users_table_arn               = aws_dynamodb_table.users.arn
  rental_invoices_table_arn     = aws_dynamodb_table.rental_invoices.arn
  jwt_secret_arn                = data.aws_secretsmanager_secret.jwt_secret.arn
  google_oauth_credentials_secret_arn = aws_secretsmanager_secret.google_oauth_credentials.arn
}

# Lambda module
module "lambdas" {
  source = "./lambdas"
  
  # Pass required variables
  aws_region                    = var.aws_region
  python_runtime               = var.python_runtime
  lambda_fetch_rental_invoices = var.lambda_fetch_rental_invoices
  lambda_fetch_latest_rental_invoice = var.lambda_fetch_latest_rental_invoice
  lambda_parse_rental_invoice  = var.lambda_parse_rental_invoice
  lambda_send_rental_invoice_notification = var.lambda_send_rental_invoice_notification
  lambda_signup_user           = var.lambda_signup_user
  lambda_login_user            = var.lambda_login_user
  lambda_delete_user           = var.lambda_delete_user
  lambda_get_rental_invoices   = var.lambda_get_rental_invoices
  lambda_get_rental_invoice    = var.lambda_get_rental_invoice
  lambda_get_user_profile      = var.lambda_get_user_profile
  lambda_gmail_store_tokens    = var.lambda_gmail_store_tokens
  invoices_table               = var.invoices_table
  rental_invoice_email         = var.rental_invoice_email
  rental_invoice_email_subject = var.rental_invoice_email_subject
  invoices_bucket_name         = var.invoices_bucket_name
  
  # Pass resource references
  lambda_bucket_id                        = aws_s3_bucket.lambda_bucket.id
  users_table_name                        = aws_dynamodb_table.users.name
  rental_invoices_table_name              = aws_dynamodb_table.rental_invoices.name
  rental_invoices_bucket_arn              = aws_s3_bucket.rental_invoices.arn
  email_access_credentials_secret_name    = aws_secretsmanager_secret.email_access_credentials.name
  jwt_secret_version_secret_string        = data.aws_secretsmanager_secret_version.jwt_secret_version.secret_string
  google_oauth_client_id                  = var.google_oauth_client_id
  sns_topic_arn                          = aws_sns_topic.new_invoice_notification.arn
  daily_lambda_trigger_arn               = aws_cloudwatch_event_rule.daily_lambda_trigger.arn
  
  # Pass IAM role ARNs from IAM module
  wallenstam_lambda_role_arn             = module.iam.wallenstam_lambda_role_arn
  signup_lambda_role_arn                 = module.iam.signup_lambda_role_arn
  delete_user_lambda_role_arn            = module.iam.delete_user_lambda_role_arn
  get_rental_invoices_lambda_role_arn    = module.iam.get_rental_invoices_lambda_role_arn
  get_rental_invoice_lambda_role_arn     = module.iam.get_rental_invoice_lambda_role_arn
  get_user_profile_lambda_role_arn       = module.iam.get_user_profile_lambda_role_arn
  gmail_store_tokens_lambda_role_arn     = module.iam.gmail_store_tokens_lambda_role_arn
}