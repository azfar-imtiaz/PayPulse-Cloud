# === This is for the rental-invoices bucket ===
resource "aws_s3_bucket" "rental_invoices" {
  bucket = var.invoices_bucket_name
}

resource "aws_s3_bucket_versioning" "rental_invoices" {
  bucket = aws_s3_bucket.rental_invoices.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "rental_invoices" {
  bucket = aws_s3_bucket.rental_invoices.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "rental_invoices" {
  bucket = aws_s3_bucket.rental_invoices.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_object" "invoices_path" {
  bucket  = aws_s3_bucket.rental_invoices.id
  key     = var.path_to_invoices
  content = ""
}

# === This is for the lambda functions bucket ===
resource "aws_s3_bucket" "lambda_bucket" {
  bucket = var.lambda_functions_bucket_name
}

resource "aws_s3_bucket_versioning" "lambda_bucket_versioning" {
  bucket = aws_s3_bucket.lambda_bucket.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_policy" "lambda_bucket_policy" {
  bucket = aws_s3_bucket.lambda_bucket.id
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Principal = {
          Service = "lambda.amazonaws.com"
        },
        Action = "s3:GetObject",
        Resource = "${aws_s3_bucket.lambda_bucket.arn}/*"
      }
    ]
  })
}

# Defining trigger for PDF upload on S3 bucket for parse_invoice lambda function
resource "aws_s3_bucket_notification" "invoice_upload_trigger" {
  bucket = aws_s3_bucket.rental_invoices.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.parse_invoice.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = var.path_to_invoices
    filter_suffix       = ".pdf"
  }

  depends_on = [aws_lambda_permission.allow_s3_invoke_parse_invoice]
}