# On-demand, single-category retail invoice fetch - the retail equivalent of
# fetch_latest_invoice (rental). Reuses the sweep/classify/upload logic in utils.retail_sweep
# (shared common layer) but scoped to a tight 12h window and one caller-specified category,
# also covering the caller's Outlook inbox when linked (best-effort, deadline-bounded),
# so a single invocation reliably finishes well inside API Gateway's fixed 30s integration
# timeout. API-Gateway-only - no EventBridge trigger.

data "aws_s3_bucket_object" "fetch_latest_retail_invoices_zip" {
  bucket = var.lambda_bucket_id
  key    = "${var.lambda_fetch_latest_retail_invoices}.zip"
}

resource "aws_lambda_function" "fetch_latest_retail_invoices" {
  function_name = var.lambda_fetch_latest_retail_invoices
  role          = var.fetch_latest_retail_invoices_lambda_role_arn
  handler       = "main.lambda_handler"
  runtime       = var.python_runtime
  timeout       = 28 # Just under API Gateway HTTP API's fixed 30s integration timeout
  memory_size   = 512

  s3_bucket         = var.lambda_bucket_id
  s3_key            = data.aws_s3_bucket_object.fetch_latest_retail_invoices_zip.key
  s3_object_version = data.aws_s3_bucket_object.fetch_latest_retail_invoices_zip.version_id

  layers = [
    aws_lambda_layer_version.utils_layer.arn,
    aws_lambda_layer_version.pyjwt_layer.arn,
    aws_lambda_layer_version.google_api_layer.arn,
    aws_lambda_layer_version.jev_layer.arn,
    aws_lambda_layer_version.google_genai_layer.arn
  ]

  environment {
    variables = {
      JWT_SECRET                               = var.jwt_secret_version_secret_string
      S3_BUCKET                                = var.invoices_bucket_name
      USERS_TABLE                              = var.users_table_name
      REGION                                   = var.aws_region
      GOOGLE_OAUTH_CLIENT_ID                   = var.google_oauth_client_id
      OUTLOOK_OAUTH_CLIENT_ID                  = var.outlook_oauth_client_id
      OUTLOOK_OAUTH_CLIENT_SECRET              = var.outlook_oauth_client_secret
      GEMINI_API_KEY                           = var.gemini_api_key_secret_string
      JEV_API_KEY                              = var.jev_api_key_secret_string
      RETAIL_EMAIL_CLASSIFICATION_LEDGER_TABLE = var.retail_email_classification_ledger_table_name
      NOUL_THRESHOLD                           = "0.5"
      CHOICE_CONFIDENCE_THRESHOLD              = "0.6"
      ON_DEMAND_SWEEP_WINDOW_HOURS             = "12"
      EXCLUDED_SENDER_EMAILS                   = var.rental_invoice_email
    }
  }
}

resource "aws_cloudwatch_log_group" "fetch_latest_retail_invoices" {
  name              = "/aws/lambda/${var.lambda_fetch_latest_retail_invoices}"
  retention_in_days = 30
}
