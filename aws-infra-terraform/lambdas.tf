data "aws_caller_identity" "current" {}

# this fetches the latest version of the fetch_invoices.zip file from S3
data "aws_s3_bucket_object" "fetch_invoices_zip" {
  bucket = aws_s3_bucket.lambda_bucket.id
  key    = "${var.lambda_fetch_rental_invoices}.zip"
}

# this fetches the latest version of the fetch_latest_invoice.zip file from S3
data "aws_s3_bucket_object" "fetch_latest_invoice_zip" {
  bucket = aws_s3_bucket.lambda_bucket.id
  key    = "${var.lambda_fetch_latest_rental_invoice}.zip"
}

# this fetches the latest version of the send_invoice_notification.zip file from S3
data "aws_s3_bucket_object" "send_invoice_notification_zip" {
  bucket = aws_s3_bucket.lambda_bucket.id
  key    = "${var.lambda_send_rental_invoice_notification}.zip"
}


# === Fetch_invoices lambda function ===
resource "aws_lambda_function" "fetch_invoices" {
  description   = "This function is a one-time trigger used to fetch all rental invoices found in the email inbox, download the PDF invoices, and upload them to the S3 bucket."
  function_name = var.lambda_fetch_rental_invoices
  handler       = "lambda_function.lambda_handler"
  runtime       = var.python_runtime
  role          = aws_iam_role.wallenstam_lambda_role.arn
  timeout       = 300 # this is in seconds, so equals 5 minutes

  environment {
    variables = {
      DYNAMODB_TABLE      = var.invoices_table
      EMAIL_CREDS         = aws_secretsmanager_secret.email_access_credentials.name
      EMAIL_SENDER        = var.rental_invoice_email
      EMAIL_SUBJECT       = var.rental_invoice_email_subject
      REGION              = var.aws_region
      S3_BUCKET           = var.invoices_bucket_name
    }
  }

  logging_config {
    log_format = "JSON"
  }

  s3_bucket         = aws_s3_bucket.lambda_bucket.id
  s3_key            = "${var.lambda_fetch_rental_invoices}.zip"
  s3_object_version = data.aws_s3_bucket_object.fetch_invoices_zip.version_id
}


# === Fetch_latest_invoice lambda function ===
resource "aws_lambda_function" "fetch_latest_invoice" {
  description   = "This function is triggered once every weekday. It checks the email to see if there is a new invoice for the current month. If found, it uploads the rental invoice PDF to the S3 bucket."
  function_name = var.lambda_fetch_latest_rental_invoice
  handler       = "main.lambda_handler"
  runtime       = var.python_runtime
  role          = aws_iam_role.wallenstam_lambda_role.arn
  timeout       = 60 # this is in seconds, so equals 1 minute

  environment {
    variables = {
      DYNAMODB_TABLE      = var.invoices_table
      EMAIL_CREDS         = aws_secretsmanager_secret.email_access_credentials.name
      EMAIL_SENDER        = var.rental_invoice_email
      EMAIL_SUBJECT       = var.rental_invoice_email_subject
      REGION              = var.aws_region
      S3_BUCKET           = var.invoices_bucket_name
    }
  }

  logging_config {
    log_format = "JSON"
  }

  s3_bucket         = aws_s3_bucket.lambda_bucket.id
  s3_key            = "${var.lambda_fetch_latest_rental_invoice}.zip"
  s3_object_version = data.aws_s3_bucket_object.fetch_latest_invoice_zip.version_id
}

# permission for daily lambda trigger to invoke this function
resource "aws_lambda_permission" "fetch_latest_invoice_event" {
  statement_id  = "AllowEventBridgeToInvokeFetchLatestInvoice"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.fetch_latest_invoice.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.daily_lambda_trigger.arn
}


# === Parse_invoice lambda function ===
resource "aws_lambda_function" "parse_invoice" {
  description   = "This function is triggered whenever a new rental invoice PDF is uploaded to the S3 bucket. It parses the function and inserts the rental invoice details into the DynamoDB table."
  function_name = var.lambda_parse_rental_invoice
  role          = aws_iam_role.wallenstam_lambda_role.arn
  package_type  = "Image"
  image_uri     = "${data.aws_caller_identity.current.account_id}.dkr.ecr.${var.aws_region}.amazonaws.com/wallenstam/invoice-parser:latest"
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
  source_arn    = aws_s3_bucket.rental_invoices.arn
}


# === Send_invoice_notification lambda function ===
resource "aws_lambda_function" "send_invoice_notification" {
  description   = "This function is triggered whenever a new record is added to the Wallenstam-Invoices DynamoDB table. It sends a SNS notification containing the invoice details."
  function_name = var.lambda_send_rental_invoice_notification
  handler       = "main.lambda_handler"
  runtime       = var.python_runtime
  role          = aws_iam_role.wallenstam_lambda_role.arn
  timeout       = 3

  environment {
    variables = {
      SNS_TOPIC_ARN = aws_sns_topic.new_invoice_notification.arn
    }
  }

  s3_bucket = aws_s3_bucket.lambda_bucket.id
  s3_key    = "${var.lambda_send_rental_invoice_notification}.zip"
}