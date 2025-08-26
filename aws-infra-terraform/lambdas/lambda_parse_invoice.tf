# === Parse_invoice lambda function ===
resource "aws_lambda_function" "parse_invoice" {
  description   = "This function is triggered whenever a new rental invoice PDF is uploaded to the S3 bucket. It parses the function and inserts the rental invoice details into the DynamoDB table."
  function_name = var.lambda_parse_rental_invoice
  role          = var.wallenstam_lambda_role_arn
  package_type  = "Image"
  # IMPORTANT: This tag at the end of the image_uri must be replaced everytime a new docker image is generated
  image_uri     = "${data.aws_caller_identity.current.account_id}.dkr.ecr.${var.aws_region}.amazonaws.com/wallenstam/invoice-parser:20250701T175847"
  timeout       = 60        # 1 minute

  environment {
    variables = {
      DYNAMODB_TABLE = var.invoices_table
      REGION         = var.aws_region
    }
  }
}

# permission for PDF upload on S3 bucket trigger
resource "aws_lambda_permission" "allow_s3_invoke_parse_invoice" {
  statement_id  = "AllowS3Invoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.parse_invoice.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = var.rental_invoices_bucket_arn
}