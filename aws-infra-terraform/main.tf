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