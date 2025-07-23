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

# this fetches the latest version of the signup_user.zip file from S3
data "aws_s3_bucket_object" "signup_user_zip" {
  bucket = aws_s3_bucket.lambda_bucket.id
  key    = "${var.lambda_signup_user}.zip"
}

# this fetches the latest version of the login_user.zip file from S3
data "aws_s3_bucket_object" "login_user_zip" {
  bucket = aws_s3_bucket.lambda_bucket.id
  key    = "${var.lambda_login_user}.zip"
}

# this fetches the latest version of the delete_user.zip file from S3
data "aws_s3_bucket_object" "delete_user_zip" {
  bucket = aws_s3_bucket.lambda_bucket.id
  key    = "${var.lambda_delete_user}.zip"
}

# this fetches the latest version of the get_rental_invoices.zip file from S3
data "aws_s3_bucket_object" "get_rental_invoices_zip" {
  bucket = aws_s3_bucket.lambda_bucket.id
  key    = "${var.lambda_get_rental_invoices}.zip"
}

# this fetches the latest version of the get_rental_invoice.zip file from S3
data "aws_s3_bucket_object" "get_rental_invoice_zip" {
  bucket = aws_s3_bucket.lambda_bucket.id
  key    = "${var.lambda_get_rental_invoice}.zip"
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
      EMAIL_SENDER        = var.rental_invoice_email
      EMAIL_SUBJECT       = var.rental_invoice_email_subject
      REGION              = var.aws_region
      S3_BUCKET           = var.invoices_bucket_name
      JWT_SECRET          = data.aws_secretsmanager_secret_version.jwt_secret_version.secret_string
    }
  }

  logging_config {
    log_format = "JSON"
  }

  layers = [
    # this layer is not needed - it's there because the lambda function imports from utils.utility_functions
    # data.klayers_package_latest_version.bcrypt.arn,
    aws_lambda_layer_version.utils_layer.arn,
    aws_lambda_layer_version.pyjwt_layer.arn
  ]

  s3_bucket         = aws_s3_bucket.lambda_bucket.id
  s3_key            = "${var.lambda_fetch_rental_invoices}.zip"
  s3_object_version = data.aws_s3_bucket_object.fetch_invoices_zip.version_id
}


# === Fetch_latest_invoice lambda function ===
resource "aws_lambda_function" "fetch_latest_invoice" {
  description   = "This function is triggered via API Gateway. It checks to see if an invoice is available for the current month, if not already parsed."
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
      JWT_SECRET  = data.aws_secretsmanager_secret_version.jwt_secret_version.secret_string
    }
  }

  logging_config {
    log_format = "JSON"
  }

  layers = [
    aws_lambda_layer_version.utils_layer.arn,
    aws_lambda_layer_version.pyjwt_layer.arn
  ]

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
  s3_object_version = data.aws_s3_bucket_object.send_invoice_notification_zip.version_id
}

# === Lambda layers for bcrypt, pyjwt, and common utils functions

data "klayers_package_latest_version" "bcrypt" {
  name   = "bcrypt"
  region = var.aws_region
}

resource "aws_lambda_layer_version" "utils_layer" {
  layer_name = "utils-layer"
  compatible_runtimes = ["python3.12"]
  filename = "../lambda_layers/common/utils_layer.zip"
  source_code_hash = filebase64sha256("../lambda_layers/common/utils_layer.zip")
}

resource "aws_lambda_layer_version" "pyjwt_layer" {
  layer_name = "pyjwt-layer"
  compatible_runtimes = ["python3.12"]
  filename = "../lambda_layers/jwt/pyjwt_layer.zip"
  source_code_hash = filebase64sha256("../lambda_layers/jwt/pyjwt_layer.zip")
}

# === Signup_user lambda function ===

resource "aws_lambda_function" "signup_user" {
  description   = "This function is triggered via the iOS app when a new user signs up. It creates a new user entry in DynamoDB, creates a folder with the UserID in rental invoices S3 bucket, and creates a secret for this user."
  function_name = var.lambda_signup_user
  handler       = "main.lambda_handler"
  runtime       = var.python_runtime
  role          = aws_iam_role.signup_lambda_role.arn

  timeout       = 15
  memory_size   = 128

  environment {
    variables = {
      USERS_TABLE = aws_dynamodb_table.users.name
      S3_BUCKET   = var.invoices_bucket_name,
      JWT_SECRET  = data.aws_secretsmanager_secret_version.jwt_secret_version.secret_string
    }
  }

  layers = [
    data.klayers_package_latest_version.bcrypt.arn,
    aws_lambda_layer_version.utils_layer.arn,
    aws_lambda_layer_version.pyjwt_layer.arn
  ]

  s3_bucket = aws_s3_bucket.lambda_bucket.id
  s3_key    = "${var.lambda_signup_user}.zip"
  s3_object_version = data.aws_s3_bucket_object.signup_user_zip.version_id
}

# === Login lambda function ===

resource "aws_lambda_function" "login_user" {
  description   = "This function is triggered via the iOS app when an existing user logs in. It receives the user's email and password, verifies the user details, and then returns the access token in the response."
  function_name = "login_user"
  role          = aws_iam_role.wallenstam_lambda_role.arn
  runtime       = "python3.9"
  handler       = "main.lambda_handler"

  timeout     = 15
  memory_size = 128

  environment {
    variables = {
      USERS_TABLE = aws_dynamodb_table.users.name
      JWT_SECRET  = data.aws_secretsmanager_secret_version.jwt_secret_version.secret_string
    }
  }

  layers = [
    data.klayers_package_latest_version.bcrypt.arn,
    aws_lambda_layer_version.pyjwt_layer.arn,
    aws_lambda_layer_version.utils_layer.arn
  ]

  s3_bucket = aws_s3_bucket.lambda_bucket.id
  s3_key    = "${var.lambda_login_user}.zip"
  s3_object_version = data.aws_s3_bucket_object.login_user_zip.version_id
}

# === Delete-user lambda function ===

resource "aws_lambda_function" "delete_user" {
  description   = "This function is used to delete a user's account from PayPulse. This deletes the user's invoices from the RentalInvoices table, their secrets, their S3 folder, and finally their record from the Users table."
  function_name = "delete_user"
  role          = aws_iam_role.delete_user_lambda_role.arn
  runtime       = var.python_runtime
  handler       = "main.lambda_handler"

  timeout       = 30
  memory_size   = 128

  environment {
    variables = {
      USERS_TABLE    = aws_dynamodb_table.users.name
      INVOICES_TABLE = aws_dynamodb_table.rental_invoices.name
      BUCKET_NAME    = var.invoices_bucket_name
      JWT_SECRET     = data.aws_secretsmanager_secret_version.jwt_secret_version.secret_string
    }
  }

  logging_config {
    log_format = "JSON"
  }

  layers = [
    aws_lambda_layer_version.pyjwt_layer.arn,
    aws_lambda_layer_version.utils_layer.arn
  ]

  s3_bucket         = aws_s3_bucket.lambda_bucket.id
  s3_key            = "${var.lambda_delete_user}.zip"
  s3_object_version = data.aws_s3_bucket_object.delete_user_zip.version_id
}

# === Get-rental-invoices lambda function ===

resource "aws_lambda_function" "get_rental_invoices" {
  description   = "This function retrieves all rental invoices for a given user."
  function_name = "get_rental_invoices"
  role          = aws_iam_role.get_rental_invoices_lambda_role.arn
  runtime       = var.python_runtime
  handler       = "main.lambda_handler"

  timeout       = 10
  memory_size   = 128

  environment {
    variables = {
      INVOICES_TABLE = aws_dynamodb_table.rental_invoices.name
      JWT_SECRET     = data.aws_secretsmanager_secret_version.jwt_secret_version.secret_string
    }
  }

  logging_config {
    log_format = "JSON"
  }

  layers = [
    aws_lambda_layer_version.pyjwt_layer.arn,
    aws_lambda_layer_version.utils_layer.arn
  ]

  s3_bucket         = aws_s3_bucket.lambda_bucket.id
  s3_key            = "${var.lambda_get_rental_invoices}.zip"
  s3_object_version = data.aws_s3_bucket_object.get_rental_invoices_zip.version_id
}

# === Get-rental-invoice lambda function ===

resource "aws_lambda_function" "get_rental_invoice" {
  description   = "This function retrieves all details for a given rental invoice ID."
  function_name = "get_rental_invoice"
  role          = aws_iam_role.get_rental_invoice_lambda_role.arn
  runtime       = var.python_runtime
  handler       = "main.lambda_handler"

  timeout       = 10
  memory_size   = 128

  environment {
    variables = {
      INVOICES_TABLE = aws_dynamodb_table.rental_invoices.name
      JWT_SECRET     = data.aws_secretsmanager_secret_version.jwt_secret_version.secret_string
    }
  }

  logging_config {
    log_format = "JSON"
  }

  layers = [
    aws_lambda_layer_version.pyjwt_layer.arn,
    aws_lambda_layer_version.utils_layer.arn
  ]

  s3_bucket         = aws_s3_bucket.lambda_bucket.id
  s3_key            = "${var.lambda_get_rental_invoice}.zip"
  s3_object_version = data.aws_s3_bucket_object.get_rental_invoice_zip.version_id
}