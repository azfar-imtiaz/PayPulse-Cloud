resource "aws_iam_role" "login_lambda_role" {
  name = "Login-Lambda-Role"

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

resource "aws_iam_policy" "login_lambda_policy" {
  name = "Login-Lambda-Policy"

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Action = [
          "dynamodb:GetItem",
          "dynamodb:Query"
        ],
        Effect = "Allow",
        Resource = aws_dynamodb_table.users.arn
      },
      {
        Action = [
          "secretsmanager:GetSecretValue"
        ],
        Effect = "Allow",
        Resource = data.aws_secretsmanager_secret.jwt_secret.arn
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "login_lambda_role_attachment" {
  role = aws_iam_role.login_lambda_role.name
  policy_arn = aws_iam_policy.login_lambda_policy.arn
}