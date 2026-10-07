# IAM Role for fetch_and_classify_retail_invoices Lambda function
# No access to the 8 detail invoice tables or the Gemini-extraction write path - extraction
# IAM stays entirely in parse_retail_invoice's role, unchanged.

resource "aws_iam_role" "fetch_and_classify_retail_invoices_lambda_role" {
  name = "Fetch-And-Classify-Retail-Invoices_Lambda_Role"

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

resource "aws_iam_policy" "fetch_and_classify_retail_invoices_lambda_policy" {
  name = "Fetch-And-Classify-Retail-Invoices_Lambda_Policy"

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
      # DynamoDB - Read/Scan/Update Users table (last_retail_sweep_fetch field)
      {
        Effect = "Allow",
        Action = [
          "dynamodb:GetItem",
          "dynamodb:Query",
          "dynamodb:Scan",
          "dynamodb:UpdateItem"
        ],
        Resource = var.users_table_arn
      },
      # DynamoDB - RetailEmailClassificationLedger read/write
      {
        Effect = "Allow",
        Action = [
          "dynamodb:PutItem",
          "dynamodb:GetItem",
          "dynamodb:UpdateItem",
          "dynamodb:Query"
        ],
        Resource = [
          var.retail_email_classification_ledger_table_arn,
          "${var.retail_email_classification_ledger_table_arn}/index/status-classified_at-index"
        ]
      },
      # S3 - ListBucket permission (required for HeadObject to return 404 instead of 403)
      {
        Effect = "Allow",
        Action = [
          "s3:ListBucket"
        ],
        Resource = "arn:aws:s3:::${var.invoices_bucket_name}"
      },
      # S3 - Upload confirmed candidate HTML files (re-triggers parse_retail_invoice)
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
      },
      # Secrets Manager - Jev and Gemini API keys (consumed as plain env vars sourced from
      # these secrets at deploy time, same pattern as the existing Gemini key, but granting
      # read access here too in case a future revision reads them at runtime instead)
      {
        Effect = "Allow",
        Action = [
          "secretsmanager:GetSecretValue"
        ],
        Resource = [
          "arn:aws:secretsmanager:${var.aws_region}:*:secret:jev/api-key*",
          "arn:aws:secretsmanager:${var.aws_region}:*:secret:gemini-api-key*"
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "fetch_and_classify_retail_invoices_lambda_policy_attachment" {
  role       = aws_iam_role.fetch_and_classify_retail_invoices_lambda_role.name
  policy_arn = aws_iam_policy.fetch_and_classify_retail_invoices_lambda_policy.arn
}
