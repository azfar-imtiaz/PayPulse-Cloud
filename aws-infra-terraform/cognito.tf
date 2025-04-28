resource "aws_cognito_identity_pool" "wallenstam_identity_pool" {
  identity_pool_name = var.identity_pool_name
  allow_unauthenticated_identities = true
}

# User pool
resource "aws_cognito_user_pool" "user_pool" {
  name = "PayPulseUserPool"

  username_attributes = ["email"]
  auto_verified_attributes = ["email"]

  password_policy {
    minimum_length    = 8
    require_lowercase = true
    require_numbers   = true
    require_symbols   = false
    require_uppercase = true
  }

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }
}

# User pool client
resource "aws_cognito_user_pool_client" "user_pool_client" {
  name         = "PayPulseUserPoolClient"
  user_pool_id = aws_cognito_user_pool.user_pool.id

  generate_secret = false

  explicit_auth_flows = [
    "ALLOW_USER_PASSWORD_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
    "ALLOW_USER_SRP_AUTH"
  ]

  prevent_user_existence_errors = "ENABLED"
}