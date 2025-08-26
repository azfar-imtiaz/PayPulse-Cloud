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
}

data "aws_caller_identity" "current" {}