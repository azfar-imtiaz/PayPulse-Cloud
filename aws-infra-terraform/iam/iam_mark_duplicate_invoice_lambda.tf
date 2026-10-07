resource "aws_iam_role" "mark_duplicate_invoice_lambda_role" {
  name = "mark_duplicate_invoice_lambda_role"
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

resource "aws_iam_policy" "mark_duplicate_invoice_lambda_policy" {
  name = "Mark-Duplicate-Invoice-Lambda-Policy"
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Action = [
          "dynamodb:Query",
          "dynamodb:UpdateItem"
        ],
        Resource = [
          var.retail_invoices_table_arn
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "mark_duplicate_invoice_lambda_basic_execution" {
  role       = aws_iam_role.mark_duplicate_invoice_lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "mark_duplicate_invoice_lambda_role_attachment" {
  role       = aws_iam_role.mark_duplicate_invoice_lambda_role.name
  policy_arn = aws_iam_policy.mark_duplicate_invoice_lambda_policy.arn
}
