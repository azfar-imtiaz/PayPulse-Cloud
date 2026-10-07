# API-triggered entry point for the historical retail invoice backfill.
# NOTE: this endpoint is untested - see lambdas/invoices/start_retail_invoice_backfill/main.py.
# The backfill itself (via the retail-invoice-backfill Step Functions state machine) has
# already been run and verified end-to-end via the CLI script
# (scripts/start_historical_retail_backfill.py) - this Lambda is the same capability
# exposed over the API for a future app-facing feature, implemented for completeness.

data "aws_s3_object" "start_retail_invoice_backfill_zip" {
  bucket = var.lambda_bucket_id
  key    = "${var.lambda_start_retail_invoice_backfill}.zip"
}

resource "aws_lambda_function" "start_retail_invoice_backfill" {
  description   = "Starts a historical retail invoice backfill (Step Functions execution) for the authenticated caller. UNTESTED."
  function_name = var.lambda_start_retail_invoice_backfill
  role          = var.start_retail_invoice_backfill_lambda_role_arn
  runtime       = var.python_runtime
  handler       = "main.lambda_handler"

  timeout     = 15
  memory_size = 128

  environment {
    variables = {
      JWT_SECRET        = var.jwt_secret_version_secret_string
      STATE_MACHINE_ARN = var.retail_invoice_backfill_state_machine_arn
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
  s3_key            = "${var.lambda_start_retail_invoice_backfill}.zip"
  s3_object_version = data.aws_s3_object.start_retail_invoice_backfill_zip.version_id
}
