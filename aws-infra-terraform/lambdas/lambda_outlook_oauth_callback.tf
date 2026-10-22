# this fetches the latest version of the outlook_oauth_callback.zip file from S3
data "aws_s3_bucket_object" "outlook_oauth_callback_zip" {
  bucket = var.lambda_bucket_id
  key    = "${var.lambda_outlook_oauth_callback}.zip"
}

# === outlook_oauth_callback lambda function ===
# Unauthenticated bounce endpoint - relays Microsoft's redirect (to the Web-platform
# redirect URI, required for the confidential-client code exchange) back to the app's
# custom URL scheme, which is all ASWebAuthenticationSession can actually intercept.
resource "aws_lambda_function" "outlook_oauth_callback" {
  description   = "Unauthenticated bounce endpoint that relays Microsoft's OAuth redirect back to the iOS app's custom URL scheme."
  function_name = var.lambda_outlook_oauth_callback
  handler       = "main.lambda_handler"
  runtime       = var.python_runtime
  role          = var.outlook_oauth_callback_lambda_role_arn

  timeout     = 10
  memory_size = 128

  s3_bucket         = var.lambda_bucket_id
  s3_key            = "${var.lambda_outlook_oauth_callback}.zip"
  s3_object_version = data.aws_s3_bucket_object.outlook_oauth_callback_zip.version_id
}
