# this fetches the latest version of the login_user.zip file from S3
data "aws_s3_bucket_object" "login_user_zip" {
  bucket = var.lambda_bucket_id
  key    = "${var.lambda_login_user}.zip"
}

# === Login lambda function ===
resource "aws_lambda_function" "login_user" {
  description   = "This function is triggered via the iOS app when an existing user logs in. It receives the user's email and password, verifies the user details, and then returns the access token in the response."
  function_name = "login_user"
  role          = var.wallenstam_lambda_role_arn
  runtime       = "python3.9"
  handler       = "main.lambda_handler"

  timeout     = 15
  memory_size = 128

  environment {
    variables = {
      USERS_TABLE = var.users_table_name
      JWT_SECRET  = var.jwt_secret_version_secret_string
    }
  }

  layers = [
    data.klayers_package_latest_version.bcrypt.arn,
    aws_lambda_layer_version.pyjwt_layer.arn,
    aws_lambda_layer_version.utils_layer.arn
  ]

  s3_bucket = var.lambda_bucket_id
  s3_key    = "${var.lambda_login_user}.zip"
  s3_object_version = data.aws_s3_bucket_object.login_user_zip.version_id
}