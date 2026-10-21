# Lambda function for the broad Outlook/Microsoft Graph sweep + Jev classification retail
# invoice discovery pipeline. Second email provider feeding the same downstream pipeline
# fetch_and_classify_retail_invoices (Gmail) feeds - shares the same retail_sweep_trigger
# EventBridge rule rather than a separate one.

data "aws_s3_bucket_object" "fetch_and_classify_outlook_invoices_zip" {
  bucket = var.lambda_bucket_id
  key    = "${var.lambda_fetch_and_classify_outlook_invoices}.zip"
}

resource "aws_lambda_function" "fetch_and_classify_outlook_invoices" {
  function_name = var.lambda_fetch_and_classify_outlook_invoices
  role          = var.fetch_and_classify_outlook_invoices_lambda_role_arn
  handler       = "lambda_function.lambda_handler"
  runtime       = var.python_runtime
  timeout       = 900 # 15 minutes
  memory_size   = 512

  s3_bucket         = var.lambda_bucket_id
  s3_key            = data.aws_s3_bucket_object.fetch_and_classify_outlook_invoices_zip.key
  s3_object_version = data.aws_s3_bucket_object.fetch_and_classify_outlook_invoices_zip.version_id

  layers = [
    aws_lambda_layer_version.utils_layer.arn,
    aws_lambda_layer_version.pyjwt_layer.arn,
    aws_lambda_layer_version.jev_layer.arn,
    aws_lambda_layer_version.google_genai_layer.arn
  ]

  environment {
    variables = {
      S3_BUCKET                                = var.invoices_bucket_name
      USERS_TABLE                              = var.users_table_name
      REGION                                   = var.aws_region
      OUTLOOK_OAUTH_CLIENT_ID                  = var.outlook_oauth_client_id
      GEMINI_API_KEY                           = var.gemini_api_key_secret_string
      JEV_API_KEY                              = var.jev_api_key_secret_string
      RETAIL_EMAIL_CLASSIFICATION_LEDGER_TABLE = var.retail_email_classification_ledger_table_name
      NOUL_THRESHOLD                           = "0.5"
      CHOICE_CONFIDENCE_THRESHOLD              = "0.6"
      MAX_SWEEP_PAGES                          = "10"
      EXCLUDED_SENDER_EMAILS                   = var.rental_invoice_email
    }
  }
}

# Lambda permission for the shared EventBridge sweep trigger - required separately from
# the Gmail fetch Lambda's own permission, since EventBridge invoking two different
# Lambdas off one rule needs a permission grant per target.
resource "aws_lambda_permission" "fetch_and_classify_outlook_invoices_eventbridge" {
  statement_id  = "AllowEventBridgeSweepTrigger"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.fetch_and_classify_outlook_invoices.function_name
  principal     = "events.amazonaws.com"
  source_arn    = var.retail_sweep_trigger_arn
}

resource "aws_cloudwatch_log_group" "fetch_and_classify_outlook_invoices" {
  name              = "/aws/lambda/${var.lambda_fetch_and_classify_outlook_invoices}"
  retention_in_days = 30
}
