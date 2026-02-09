# Lambda function for creating manual retail invoices

data "aws_s3_bucket_object" "create_manual_invoice_zip" {
  bucket = var.lambda_bucket_id
  key    = "${var.lambda_create_manual_invoice}.zip"
}

resource "aws_lambda_function" "create_manual_invoice" {
  description   = "This function creates manual retail invoices directly through API calls, allowing users to input invoice data manually rather than fetching from email."
  function_name = var.lambda_create_manual_invoice
  role          = var.create_manual_invoice_lambda_role_arn
  runtime       = var.python_runtime
  handler       = "main.lambda_handler"

  timeout     = 30  # 30 seconds for manual data processing
  memory_size = 256

  s3_bucket         = var.lambda_bucket_id
  s3_key            = data.aws_s3_bucket_object.create_manual_invoice_zip.key
  s3_object_version = data.aws_s3_bucket_object.create_manual_invoice_zip.version_id

  environment {
    variables = {
      JWT_SECRET                        = var.jwt_secret_version_secret_string
      RETAIL_INVOICES_TABLE             = var.retail_invoices_table_name
      FOOD_DELIVERY_INVOICES_TABLE      = var.food_delivery_invoices_table_name
      CLOTHING_INVOICES_TABLE           = var.clothing_invoices_table_name
      TECHNOLOGY_INVOICES_TABLE         = var.technology_invoices_table_name
      SUBSCRIPTION_INVOICES_TABLE       = var.subscription_invoices_table_name
      GROCERY_INVOICES_TABLE            = var.grocery_invoices_table_name
      MISC_UTILITY_INVOICES_TABLE       = var.misc_utility_invoices_table_name
      MISC_INVOICES_TABLE               = var.misc_invoices_table_name
      TRAVEL_INVOICES_TABLE             = var.travel_invoices_table_name
    }
  }

  layers = [
    data.klayers_package_latest_version.bcrypt.arn,
    aws_lambda_layer_version.utils_layer.arn,
    aws_lambda_layer_version.pyjwt_layer.arn
  ]

  logging_config {
    log_format = "JSON"
  }
}

# CloudWatch log group
resource "aws_cloudwatch_log_group" "create_manual_invoice" {
  name              = "/aws/lambda/${var.lambda_create_manual_invoice}"
  retention_in_days = 30
}