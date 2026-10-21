resource "aws_iam_role" "outlook_store_tokens_lambda_role" {
  name = "Outlook-Store-Tokens-Lambda-Role"

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

resource "aws_iam_policy" "outlook_store_tokens_lambda_policy" {
  name = "Outlook-Store-Tokens-Lambda-Policy"

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
          "arn:aws:secretsmanager:*:*:secret:outlook/user/*"
        ]
      },
      # S3 - PutObject to create the user's folder structure. Unlike Gmail's store-tokens
      # Lambda (which never actually got S3_BUCKET wired, making this path dead in
      # production), this path is live, so the permission is needed from the start.
      {
        Action = [
          "s3:PutObject"
        ],
        Effect   = "Allow",
        Resource = "arn:aws:s3:::${var.invoices_bucket_name}/invoices/*"
      },
      {
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ],
        Effect   = "Allow",
        Resource = "arn:aws:logs:*:*:*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "outlook_store_tokens_lambda_basic_execution" {
  role       = aws_iam_role.outlook_store_tokens_lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "outlook_store_tokens_lambda_role_attachment" {
  role       = aws_iam_role.outlook_store_tokens_lambda_role.name
  policy_arn = aws_iam_policy.outlook_store_tokens_lambda_policy.arn
}
