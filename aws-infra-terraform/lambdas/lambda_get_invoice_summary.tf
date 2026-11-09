# this fetches the latest version of the get_invoice_summary.zip file from S3
data "aws_s3_bucket_object" "get_invoice_summary_zip" {
  bucket = var.lambda_bucket_id
  key    = "${var.lambda_get_invoice_summary}.zip"
}

# === Get-invoice-summary lambda function (home screen: current-month rental + retail spend) ===
resource "aws_lambda_function" "get_invoice_summary" {
  description   = "This function returns the current-month rental + retail spend summary for a given user."
  function_name = "get_invoice_summary"
  role          = var.get_invoice_summary_lambda_role_arn
  runtime       = var.python_runtime
  handler       = "main.lambda_handler"

  timeout     = 15
  memory_size = 256

  environment {
    variables = {
      RENTAL_INVOICES_TABLE = var.rental_invoices_table_name
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
  s3_key            = "${var.lambda_get_invoice_summary}.zip"
  s3_object_version = data.aws_s3_bucket_object.get_invoice_summary_zip.version_id
}
