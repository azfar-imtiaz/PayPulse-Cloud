# this fetches the latest version of the send_invoice_notification.zip file from S3
data "aws_s3_bucket_object" "send_invoice_notification_zip" {
  bucket = var.lambda_bucket_id
  key    = "${var.lambda_send_rental_invoice_notification}.zip"
}

# === Send_invoice_notification lambda function ===
resource "aws_lambda_function" "send_invoice_notification" {
  description   = "This function is triggered whenever a new record is added to the Wallenstam-Invoices DynamoDB table. It sends a SNS notification containing the invoice details."
  function_name = var.lambda_send_rental_invoice_notification
  handler       = "main.lambda_handler"
  runtime       = var.python_runtime
  role          = var.wallenstam_lambda_role_arn
  timeout       = 3

  environment {
    variables = {
      SNS_TOPIC_ARN = var.sns_topic_arn
    }
  }

  s3_bucket = var.lambda_bucket_id
  s3_key    = "${var.lambda_send_rental_invoice_notification}.zip"
  s3_object_version = data.aws_s3_bucket_object.send_invoice_notification_zip.version_id
}