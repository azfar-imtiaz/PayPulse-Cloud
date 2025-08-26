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
}