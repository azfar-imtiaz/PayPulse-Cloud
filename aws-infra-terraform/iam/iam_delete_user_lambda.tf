resource "aws_iam_role" "delete_user_lambda_role" {
  name = "delete_user_lambda_role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Action    = "sts:AssumeRole",
      Effect    = "Allow",
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_policy" "delete_user_lambda_policy" {
  name = "Delete-User_Lambda_Policy"
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Action = [
          "dynamodb:Query",
          "dynamodb:DeleteItem",
          "dynamodb:Scan"
        ],
        Resource = [
          var.rental_invoices_table_arn,
          var.users_table_arn
        ]
      },
      {
        Effect = "Allow",
        Action = [
          "s3:ListBucket",
          "s3:DeleteObject"
        ],
        Resource = [
          "arn:aws:s3:::${var.invoices_bucket_name}",
          "arn:aws:s3:::${var.invoices_bucket_name}/*"
        ]
      },
      {
        Effect = "Allow",
        Action = [
          "secretsmanager:DeleteSecret"
        ],
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "delete_user_lambda_basic_execution" {
  role       = aws_iam_role.delete_user_lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "delete_user_lambda_role_attachment" {
  role       = aws_iam_role.delete_user_lambda_role.name
  policy_arn = aws_iam_policy.delete_user_lambda_policy.arn
}