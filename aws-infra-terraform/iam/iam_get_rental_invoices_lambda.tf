resource "aws_iam_role" "get_rental_invoices_lambda_role" {
  name = "get_rental_invoices_lambda_role"
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

resource "aws_iam_policy" "get_rental_invoices_lambda_policy" {
  name = "Get-Rental-Invoices-Lambda-Policy"
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Action = [
          "dynamodb:Query"
        ],
        Resource = var.rental_invoices_table_arn
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "get_rental_invoices_lambda_basic_execution" {
  role       = aws_iam_role.get_rental_invoices_lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "get_rental_invoices_lambda_role_attachment" {
  role       = aws_iam_role.get_rental_invoices_lambda_role.name
  policy_arn = aws_iam_policy.get_rental_invoices_lambda_policy.arn
}