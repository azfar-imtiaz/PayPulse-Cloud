# this fetches the latest version of the get_rental_invoice.zip file from S3
data "aws_s3_bucket_object" "get_rental_invoice_zip" {
  bucket = var.lambda_bucket_id
  key    = "${var.lambda_get_rental_invoice}.zip"
}

# === Get-rental-invoice lambda function ===
resource "aws_lambda_function" "get_rental_invoice" {
  description   = "This function retrieves all details for a given rental invoice ID."
  function_name = "get_rental_invoice"
  role          = var.get_rental_invoice_lambda_role_arn
  runtime       = var.python_runtime
  handler       = "main.lambda_handler"

  timeout       = 10
  memory_size   = 128

  environment {
    variables = {
      INVOICES_TABLE = var.rental_invoices_table_name
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
  s3_key            = "${var.lambda_get_rental_invoice}.zip"
  s3_object_version = data.aws_s3_bucket_object.get_rental_invoice_zip.version_id
}