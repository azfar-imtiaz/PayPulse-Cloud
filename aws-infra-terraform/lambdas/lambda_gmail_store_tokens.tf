# this fetches the latest version of the gmail_store_tokens.zip file from S3
data "aws_s3_bucket_object" "gmail_store_tokens_zip" {
  bucket = var.lambda_bucket_id
  key    = "${var.lambda_gmail_store_tokens}.zip"
}

# === gmail_store_tokens lambda function ===
resource "aws_lambda_function" "gmail_store_tokens" {
  description   = "This function stores OAuth tokens received from iOS app for Gmail API access."
  function_name = var.lambda_gmail_store_tokens
  handler       = "main.lambda_handler"
  runtime       = var.python_runtime
  role          = var.gmail_store_tokens_lambda_role_arn

  timeout       = 15
  memory_size   = 128

  environment {
    variables = {
      JWT_SECRET            = var.jwt_secret_version_secret_string
      REGION                = var.aws_region
      GOOGLE_OAUTH_CLIENT_ID = var.google_oauth_client_id
    }
  }

  layers = [
    aws_lambda_layer_version.utils_layer.arn,
    aws_lambda_layer_version.pyjwt_layer.arn
  ]

  s3_bucket = var.lambda_bucket_id
  s3_key    = "${var.lambda_gmail_store_tokens}.zip"
  s3_object_version = data.aws_s3_bucket_object.gmail_store_tokens_zip.version_id
}