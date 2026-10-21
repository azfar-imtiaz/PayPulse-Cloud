resource "aws_iam_role" "gmail_store_tokens_lambda_role" {
  name = "Gmail-Store-Tokens-Lambda-Role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Action = "sts:AssumeRole",
      Effect = "Allow",
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_policy" "gmail_store_tokens_lambda_policy" {
  name = "Gmail-Store-Tokens-Lambda-Policy"

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Action = [
          "secretsmanager:CreateSecret",
          "secretsmanager:UpdateSecret",
          "secretsmanager:PutSecretValue",
          "secretsmanager:GetSecretValue"
        ],
        Effect = "Allow",
        Resource = [
          "arn:aws:secretsmanager:*:*:secret:gmail/user/*",
          var.google_oauth_client_id_secret_arn
        ]
      },
      {
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ],
        Effect   = "Allow",
        Resource = "arn:aws:logs:*:*:*"
      },
      # S3 - PutObject to create the user's folder structure. Previously dead code (no
      # S3_BUCKET env var was wired, so this call path never ran) - now that S3_BUCKET is
      # set and the undefined-function bug is fixed, this path actually executes.
      {
        Action = [
          "s3:PutObject"
        ],
        Effect   = "Allow",
        Resource = "arn:aws:s3:::${var.invoices_bucket_name}/invoices/*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "gmail_store_tokens_lambda_basic_execution" {
  role       = aws_iam_role.gmail_store_tokens_lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "gmail_store_tokens_lambda_role_attachment" {
  role       = aws_iam_role.gmail_store_tokens_lambda_role.name
  policy_arn = aws_iam_policy.gmail_store_tokens_lambda_policy.arn
}