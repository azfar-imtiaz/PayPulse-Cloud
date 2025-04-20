resource "aws_secretsmanager_secret" "email_access_credentials" {
  name        = "Email-Access-Credentials"
  description = "These are the credentials to access the Gmail inbox programmatically."
}

resource "aws_secretsmanager_secret_version" "email_access_credentials_value" {
  secret_id     = aws_secretsmanager_secret.email_access_credentials.id
  secret_string = var.gmail_secret_credentials
}