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
          var.google_oauth_credentials_secret_arn
        ]
      },
      {
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream", 
          "logs:PutLogEvents"
        ],
        Effect = "Allow",
        Resource = "arn:aws:logs:*:*:*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "gmail_store_tokens_lambda_basic_execution" {
  role       = aws_iam_role.gmail_store_tokens_lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "gmail_store_tokens_lambda_role_attachment" {
  role = aws_iam_role.gmail_store_tokens_lambda_role.name
  policy_arn = aws_iam_policy.gmail_store_tokens_lambda_policy.arn
}