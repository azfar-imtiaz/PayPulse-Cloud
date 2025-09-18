
data "aws_secretsmanager_secret" "jwt_secret" {
  name = "PayPulseAppJWTSecret"
}

data "aws_secretsmanager_secret_version" "jwt_secret_version" {
  secret_id = data.aws_secretsmanager_secret.jwt_secret.id
}

# Google OAuth client ID for Gmail API access
resource "aws_secretsmanager_secret" "google_oauth_client_id" {
  name        = "Google-OAuth-Client-ID"
  description = "Google OAuth client ID for Gmail API access via iOS app."
}

resource "aws_secretsmanager_secret_version" "google_oauth_client_id_value" {
  secret_id     = aws_secretsmanager_secret.google_oauth_client_id.id
  secret_string = var.google_oauth_client_id
}
