# IAM Role for fetch_retail_invoices Lambda function

resource "aws_iam_role" "fetch_retail_invoices_lambda_role" {
  name = "Fetch-Retail-Invoices_Lambda_Role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Action = "sts:AssumeRole",
        Effect = "Allow",
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_policy" "fetch_retail_invoices_lambda_policy" {
  name = "Fetch-Retail-Invoices_Lambda_Policy"

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      # CloudWatch Logs
      {
        Effect = "Allow",
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ],
        Resource = "arn:aws:logs:*:*:*"
      },
      # DynamoDB - Read Users table
      {
        Effect = "Allow",
        Action = [
          "dynamodb:GetItem",
          "dynamodb:Query"
        ],
        Resource = var.users_table_arn
      },
      # DynamoDB - Scan VendorConfig table
      {
        Effect = "Allow",
        Action = [
          "dynamodb:Scan"
        ],
        Resource = var.vendor_config_table_arn
      },
      # DynamoDB - Update Users table (last_retail_invoice_fetch field)
      {
        Effect = "Allow",
        Action = [
          "dynamodb:UpdateItem"
        ],
        Resource = var.users_table_arn
      },
      # S3 - ListBucket permission (required for HeadObject to return 404 instead of 403)
      {
        Effect = "Allow",
        Action = [
          "s3:ListBucket"
        ],
        Resource = "arn:aws:s3:::${var.invoices_bucket_name}"
      },
      # S3 - Upload retail invoice HTML files
      {
        Effect = "Allow",
        Action = [
          "s3:PutObject",
          "s3:GetObject",
          "s3:HeadObject"
        ],
        Resource = "arn:aws:s3:::${var.invoices_bucket_name}/invoices/*/retail/*/*"
      },
      # Secrets Manager - Get OAuth tokens
      {
        Effect = "Allow",
        Action = [
          "secretsmanager:GetSecretValue"
        ],
        Resource = "arn:aws:secretsmanager:${var.aws_region}:*:secret:gmail/user/*"
      },
      # Secrets Manager - Update OAuth tokens (for token refresh)
      {
        Effect = "Allow",
        Action = [
          "secretsmanager:PutSecretValue",
          "secretsmanager:UpdateSecret"
        ],
        Resource = "arn:aws:secretsmanager:${var.aws_region}:*:secret:gmail/user/*"
      },
      # Secrets Manager - Delete OAuth tokens (for expired refresh tokens)
      {
        Effect = "Allow",
        Action = [
          "secretsmanager:DeleteSecret"
        ],
        Resource = "arn:aws:secretsmanager:${var.aws_region}:*:secret:gmail/user/*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "fetch_retail_invoices_lambda_policy_attachment" {
  role       = aws_iam_role.fetch_retail_invoices_lambda_role.name
  policy_arn = aws_iam_policy.fetch_retail_invoices_lambda_policy.arn
}