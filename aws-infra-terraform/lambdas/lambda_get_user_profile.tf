# this fetches the latest version of the get_user_profile.zip file from S3
data "aws_s3_bucket_object" "get_user_profile_zip" {
  bucket = var.lambda_bucket_id
  key    = "${var.lambda_get_user_profile}.zip"
}

# === Get-user-profile lambda function ===
resource "aws_lambda_function" "get_user_profile" {
  description   = "This function retrieves the profile information for the authenticated user."
  function_name = "get_user_profile"
  role          = var.get_user_profile_lambda_role_arn
  runtime       = var.python_runtime
  handler       = "main.lambda_handler"

  timeout       = 10
  memory_size   = 128

  environment {
    variables = {
      USERS_TABLE = var.users_table_name
      JWT_SECRET  = var.jwt_secret_version_secret_string
      REGION      = var.aws_region
    }
  }

  logging_config {
    log_format = "JSON"
  }

  layers = [
    aws_lambda_layer_version.pyjwt_layer.arn,
    aws_lambda_layer_version.utils_layer.arn
  ]

  s3_bucket         = var.lambda_bucket_id
  s3_key            = "${var.lambda_get_user_profile}.zip"
  s3_object_version = data.aws_s3_bucket_object.get_user_profile_zip.version_id
}