# Lambda function for fetching retail invoices from Gmail

data "aws_s3_bucket_object" "fetch_retail_invoices_zip" {
  bucket = var.lambda_bucket_id
  key    = "${var.lambda_fetch_retail_invoices}.zip"
}

resource "aws_lambda_function" "fetch_retail_invoices" {
  function_name = var.lambda_fetch_retail_invoices
  role          = var.fetch_retail_invoices_lambda_role_arn
  handler       = "lambda_function.lambda_handler"
  runtime       = var.python_runtime
  timeout       = 900  # 15 minutes
  memory_size   = 512

  s3_bucket         = var.lambda_bucket_id
  s3_key            = data.aws_s3_bucket_object.fetch_retail_invoices_zip.key
  s3_object_version = data.aws_s3_bucket_object.fetch_retail_invoices_zip.version_id

  layers = [
    aws_lambda_layer_version.utils_layer.arn,
    aws_lambda_layer_version.pyjwt_layer.arn,
    aws_lambda_layer_version.google_api_layer.arn
  ]

  environment {
    variables = {
      JWT_SECRET             = var.jwt_secret_version_secret_string
      S3_BUCKET              = var.invoices_bucket_name
      USERS_TABLE            = var.users_table_name
      VENDOR_CONFIG_TABLE    = var.vendor_config_table_name
      REGION                 = var.aws_region
      GOOGLE_OAUTH_CLIENT_ID = var.google_oauth_client_id
    }
  }
}

# Lambda permission for EventBridge weekly trigger
resource "aws_lambda_permission" "fetch_retail_invoices_eventbridge" {
  statement_id  = "AllowEventBridgeWeeklyTrigger"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.fetch_retail_invoices.function_name
  principal     = "events.amazonaws.com"
  source_arn    = var.weekly_retail_trigger_arn
}

resource "aws_cloudwatch_log_group" "fetch_retail_invoices" {
  name              = "/aws/lambda/${var.lambda_fetch_retail_invoices}"
  retention_in_days = 30
}