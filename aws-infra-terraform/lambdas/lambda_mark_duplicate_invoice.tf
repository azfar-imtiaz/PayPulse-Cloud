# This fetches the latest version of the mark_duplicate_invoice.zip file from S3
data "aws_s3_object" "mark_duplicate_invoice_zip" {
  bucket = var.lambda_bucket_id
  key    = "${var.lambda_mark_duplicate_invoice}.zip"
}

# === Mark-duplicate-invoice lambda function ===
resource "aws_lambda_function" "mark_duplicate_invoice" {
  description   = "This function marks a retail invoice as a duplicate of another, for a given user."
  function_name = var.lambda_mark_duplicate_invoice
  role          = var.mark_duplicate_invoice_lambda_role_arn
  runtime       = var.python_runtime
  handler       = "main.lambda_handler"

  timeout     = 15
  memory_size = 128

  environment {
    variables = {
      RETAIL_INVOICES_TABLE = var.retail_invoices_table_name
      JWT_SECRET            = var.jwt_secret_version_secret_string
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
  s3_key            = "${var.lambda_mark_duplicate_invoice}.zip"
  s3_object_version = data.aws_s3_object.mark_duplicate_invoice_zip.version_id
}
