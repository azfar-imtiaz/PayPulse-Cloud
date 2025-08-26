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
        Resource = var.users_table_arn
      },
      {
        Action = [
          "dynamodb:Query"
        ],
        Effect = "Allow",
        Resource = [
          var.users_table_arn,
          "${var.users_table_arn}/index/Email-index"
        ]
      },
      {
        Action = [
          "s3:PutObject"
        ],
        Effect = "Allow",
        Resource = "arn:aws:s3:::${var.invoices_bucket_name}/*"
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