# this fetches the latest version of the fetch_latest_invoice.zip file from S3
data "aws_s3_bucket_object" "fetch_latest_invoice_zip" {
  bucket = var.lambda_bucket_id
  key    = "${var.lambda_fetch_latest_rental_invoice}.zip"
}

# === Fetch_latest_invoice lambda function ===
resource "aws_lambda_function" "fetch_latest_invoice" {
  description   = "This function is triggered via API Gateway. It checks to see if an invoice is available for the current month, if not already parsed."
  function_name = var.lambda_fetch_latest_rental_invoice
  handler       = "main.lambda_handler"
  runtime       = var.python_runtime
  role          = var.wallenstam_lambda_role_arn
  timeout       = 60 # this is in seconds, so equals 1 minute

  environment {
    variables = {
      DYNAMODB_TABLE        = var.invoices_table
      EMAIL_SENDER          = var.rental_invoice_email
      EMAIL_SUBJECT         = var.rental_invoice_email_subject
      REGION                = var.aws_region
      S3_BUCKET             = var.invoices_bucket_name
      JWT_SECRET               = var.jwt_secret_version_secret_string
      GOOGLE_OAUTH_CLIENT_ID   = var.google_oauth_client_id
    }
  }

  logging_config {
    log_format = "JSON"
  }

  layers = [
    aws_lambda_layer_version.utils_layer.arn,
    aws_lambda_layer_version.pyjwt_layer.arn,
    aws_lambda_layer_version.google_api_layer.arn
  ]

  s3_bucket         = var.lambda_bucket_id
  s3_key            = "${var.lambda_fetch_latest_rental_invoice}.zip"
  s3_object_version = data.aws_s3_bucket_object.fetch_latest_invoice_zip.version_id
}

# permission for daily lambda trigger to invoke this function
resource "aws_lambda_permission" "fetch_latest_invoice_event" {
  statement_id  = "AllowEventBridgeToInvokeFetchLatestInvoice"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.fetch_latest_invoice.function_name
  principal     = "events.amazonaws.com"
  source_arn    = var.daily_lambda_trigger_arn
}