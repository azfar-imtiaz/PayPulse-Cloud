# this fetches the latest version of the parse_retail_invoice.zip file from S3
data "aws_s3_bucket_object" "parse_retail_invoice_zip" {
  bucket = var.lambda_bucket_id
  key    = "${var.lambda_parse_retail_invoice}.zip"
}

# === Parse-retail-invoice lambda function ===
resource "aws_lambda_function" "parse_retail_invoice" {
  description   = "This function is triggered whenever a new retail invoice HTML file is uploaded to the S3 bucket. It parses the HTML using Gemini API and inserts the retail invoice details into the DynamoDB tables."
  function_name = var.lambda_parse_retail_invoice
  role          = var.parse_retail_invoice_lambda_role_arn
  runtime       = var.python_runtime
  handler       = "main.lambda_handler"

  timeout     = 60  # 1 minute for Gemini API calls
  memory_size = 256  # Increased memory for AI processing

  environment {
    variables = {
      RETAIL_INVOICES_TABLE             = var.retail_invoices_table_name
      FOOD_DELIVERY_INVOICES_TABLE      = var.food_delivery_invoices_table_name
      CLOTHING_INVOICES_TABLE           = var.clothing_invoices_table_name
      TECHNOLOGY_INVOICES_TABLE         = var.technology_invoices_table_name
      SUBSCRIPTION_INVOICES_TABLE       = var.subscription_invoices_table_name
      GROCERY_INVOICES_TABLE            = var.grocery_invoices_table_name
      MISC_UTILITY_INVOICES_TABLE       = var.misc_utility_invoices_table_name
      MISC_INVOICES_TABLE               = var.misc_invoices_table_name
      GEMINI_API_KEY                    = var.gemini_api_key_secret_string
    }
  }

  logging_config {
    log_format = "JSON"
  }

  layers = [
    aws_lambda_layer_version.utils_layer.arn,
    aws_lambda_layer_version.gemini_parsers_layer.arn,
    aws_lambda_layer_version.google_genai_layer.arn
  ]

  s3_bucket         = var.lambda_bucket_id
  s3_key            = "${var.lambda_parse_retail_invoice}.zip"
  s3_object_version = data.aws_s3_bucket_object.parse_retail_invoice_zip.version_id
}

# Permission for HTML upload on S3 bucket trigger
resource "aws_lambda_permission" "allow_s3_invoke_parse_retail_invoice" {
  statement_id  = "AllowS3Invoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.parse_retail_invoice.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = var.rental_invoices_bucket_arn
}