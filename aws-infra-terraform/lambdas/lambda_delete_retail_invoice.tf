# This fetches the latest version of the delete_retail_invoice.zip file from S3
data "aws_s3_object" "delete_retail_invoice_zip" {
  bucket = var.lambda_bucket_id
  key    = "${var.lambda_delete_retail_invoice}.zip"
}

# === Delete-retail-invoice lambda function ===
resource "aws_lambda_function" "delete_retail_invoice" {
  description   = "This function deletes a retail invoice (hard delete from DynamoDB and S3) for a given user."
  function_name = "delete_retail_invoice"
  role          = var.delete_retail_invoice_lambda_role_arn
  runtime       = var.python_runtime
  handler       = "main.lambda_handler"

  timeout     = 15
  memory_size = 128

  environment {
    variables = {
      RETAIL_INVOICES_TABLE        = var.retail_invoices_table_name
      BUCKET_NAME                  = var.invoices_bucket_name
      JWT_SECRET                   = var.jwt_secret_version_secret_string
      FOOD_DELIVERY_INVOICES_TABLE = var.food_delivery_invoices_table_name
      CLOTHING_INVOICES_TABLE      = var.clothing_invoices_table_name
      TECHNOLOGY_INVOICES_TABLE    = var.technology_invoices_table_name
      SUBSCRIPTION_INVOICES_TABLE  = var.subscription_invoices_table_name
      GROCERY_INVOICES_TABLE       = var.grocery_invoices_table_name
      MISC_UTILITY_INVOICES_TABLE  = var.misc_utility_invoices_table_name
      MISC_INVOICES_TABLE          = var.misc_invoices_table_name
      TRAVEL_INVOICES_TABLE        = var.travel_invoices_table_name
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
  s3_key            = "${var.lambda_delete_retail_invoice}.zip"
  s3_object_version = data.aws_s3_object.delete_retail_invoice_zip.version_id
}
