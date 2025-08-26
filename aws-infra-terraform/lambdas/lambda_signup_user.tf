# this fetches the latest version of the signup_user.zip file from S3
data "aws_s3_bucket_object" "signup_user_zip" {
  bucket = var.lambda_bucket_id
  key    = "${var.lambda_signup_user}.zip"
}

# === Signup_user lambda function ===
resource "aws_lambda_function" "signup_user" {
  description   = "This function is triggered via the iOS app when a new user signs up. It creates a new user entry in DynamoDB, creates a folder with the UserID in rental invoices S3 bucket, and creates a secret for this user."
  function_name = var.lambda_signup_user
  handler       = "main.lambda_handler"
  runtime       = var.python_runtime
  role          = var.signup_lambda_role_arn

  timeout       = 15
  memory_size   = 128

  environment {
    variables = {
      USERS_TABLE = var.users_table_name
      S3_BUCKET   = var.invoices_bucket_name,
      JWT_SECRET  = var.jwt_secret_version_secret_string
    }
  }

  layers = [
    data.klayers_package_latest_version.bcrypt.arn,
    aws_lambda_layer_version.utils_layer.arn,
    aws_lambda_layer_version.pyjwt_layer.arn
  ]

  s3_bucket = var.lambda_bucket_id
  s3_key    = "${var.lambda_signup_user}.zip"
  s3_object_version = data.aws_s3_bucket_object.signup_user_zip.version_id
}