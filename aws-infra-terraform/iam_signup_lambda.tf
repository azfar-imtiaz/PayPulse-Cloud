resource "aws_iam_role" "signup_lambda_role" {
  name = "Signup-Lambda-Role"

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

resource "aws_iam_policy" "signup_lambda_policy" {
  name = "Signup-Lambda-Policy"

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Action = [
          "dynamodb:PutItem",
          "dynamodb:GetItem"
        ],
        Effect = "Allow",
        Resource = aws_dynamodb_table.users.arn
      },
      {
        Action = [
          "dynamodb:Query"
        ],
        Effect = "Allow",
        Resource = [
          aws_dynamodb_table.users.arn,
          "arn:aws:dynamodb:eu-west-1:${data.aws_caller_identity.current.account_id}:table/Users/index/Email-index"
        ]
      },
      {
        Action = [
          "s3:PutObject"
        ],
        Effect = "Allow",
        Resource = "arn:aws:s3:::rental-invoices-bucket/rental-invoices/*"
      },
      {
        Action = [
          "secretsmanager:CreateSecret",
          "secretsmanager:PutSecretValue"
        ],
        Effect = "Allow",
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "signup_lambda_role_attachment" {
  role = aws_iam_role.signup_lambda_role.name
  policy_arn = aws_iam_policy.signup_lambda_policy.arn
}