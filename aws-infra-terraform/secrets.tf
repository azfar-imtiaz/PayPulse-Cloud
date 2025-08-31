# TODO: This should not be used in the future. Each user's secret should be fetched and used individually
resource "aws_secretsmanager_secret" "email_access_credentials" {
  name        = "Email-Access-Credentials"
  description = "These are the credentials to access the Gmail inbox programmatically."
}

resource "aws_secretsmanager_secret_version" "email_access_credentials_value" {
  secret_id     = aws_secretsmanager_secret.email_access_credentials.id
  secret_string = var.gmail_secret_credentials
}

data "aws_secretsmanager_secret" "jwt_secret" {
  name = "PayPulseAppJWTSecret"
}

data "aws_secretsmanager_secret_version" "jwt_secret_version" {
  secret_id = data.aws_secretsmanager_secret.jwt_secret.id
}

# Google OAuth credentials for Gmail API access
resource "aws_secretsmanager_secret" "google_oauth_credentials" {
  name        = "Google-OAuth-Credentials"
  description = "Google OAuth client credentials for Gmail API access via iOS app."
}

resource "aws_secretsmanager_secret_version" "google_oauth_credentials_value" {
  secret_id     = aws_secretsmanager_secret.google_oauth_credentials.id
  secret_string = var.google_oauth_client_id
}