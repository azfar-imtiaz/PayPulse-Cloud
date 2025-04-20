resource "aws_cognito_identity_pool" "wallenstam_identity_pool" {
  identity_pool_name = var.identity_pool_name
  allow_unauthenticated_identities = true
}