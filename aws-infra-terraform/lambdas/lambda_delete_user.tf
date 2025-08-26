# this fetches the latest version of the delete_user.zip file from S3
data "aws_s3_bucket_object" "delete_user_zip" {
  bucket = var.lambda_bucket_id
  key    = "${var.lambda_delete_user}.zip"
}

# === Delete-user lambda function ===
resource "aws_lambda_function" "delete_user" {
  description   = "This function is used to delete a user's account from PayPulse. This deletes the user's invoices from the RentalInvoices table, their secrets, their S3 folder, and finally their record from the Users table."
  function_name = "delete_user"
  role          = var.delete_user_lambda_role_arn
  runtime       = var.python_runtime
  handler       = "main.lambda_handler"

  timeout       = 30
  memory_size   = 128

  environment {
    variables = {
      USERS_TABLE    = var.users_table_name
      INVOICES_TABLE = var.rental_invoices_table_name
      BUCKET_NAME    = var.invoices_bucket_name
      JWT_SECRET     = var.jwt_secret_version_secret_string
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
  s3_key            = "${var.lambda_delete_user}.zip"
  s3_object_version = data.aws_s3_bucket_object.delete_user_zip.version_id
}