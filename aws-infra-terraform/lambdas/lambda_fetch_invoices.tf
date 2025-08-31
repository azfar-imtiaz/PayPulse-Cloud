# this fetches the latest version of the fetch_invoices.zip file from S3
data "aws_s3_bucket_object" "fetch_invoices_zip" {
  bucket = var.lambda_bucket_id
  key    = "${var.lambda_fetch_rental_invoices}.zip"
}

# === Fetch_invoices lambda function ===
resource "aws_lambda_function" "fetch_invoices" {
  description   = "This function is a one-time trigger used to fetch all rental invoices found in the email inbox, download the PDF invoices, and upload them to the S3 bucket."
  function_name = var.lambda_fetch_rental_invoices
  handler       = "lambda_function.lambda_handler"
  runtime       = var.python_runtime
  role          = var.wallenstam_lambda_role_arn
  timeout       = 300 # this is in seconds, so equals 5 minutes

  environment {
    variables = {
      DYNAMODB_TABLE        = var.invoices_table
      EMAIL_SENDER          = var.rental_invoice_email
      EMAIL_SUBJECT         = var.rental_invoice_email_subject
      REGION                = var.aws_region
      S3_BUCKET             = var.invoices_bucket_name
      JWT_SECRET            = var.jwt_secret_version_secret_string
      GOOGLE_OAUTH_CLIENT_ID = var.google_oauth_client_id
    }
  }

  logging_config {
    log_format = "JSON"
  }

  layers = [
    # this layer is not needed - it's there because the lambda function imports from utils.utility_functions
    # data.klayers_package_latest_version.bcrypt.arn,
    aws_lambda_layer_version.utils_layer.arn,
    aws_lambda_layer_version.pyjwt_layer.arn
  ]

  s3_bucket         = var.lambda_bucket_id
  s3_key            = "${var.lambda_fetch_rental_invoices}.zip"
  s3_object_version = data.aws_s3_bucket_object.fetch_invoices_zip.version_id
}