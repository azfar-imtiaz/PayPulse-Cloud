resource "aws_iam_role" "get_invoice_summary_lambda_role" {
  name = "get_invoice_summary_lambda_role"
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

resource "aws_iam_policy" "get_invoice_summary_lambda_policy" {
  name = "Get-Invoice-Summary-Lambda-Policy"
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Action = [
          "dynamodb:Query"
        ],
        Resource = [
          var.rental_invoices_table_arn,
          var.retail_invoices_table_arn,
          "${var.retail_invoices_table_arn}/index/invoice_date-index"
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "get_invoice_summary_lambda_basic_execution" {
  role       = aws_iam_role.get_invoice_summary_lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "get_invoice_summary_lambda_role_attachment" {
  role       = aws_iam_role.get_invoice_summary_lambda_role.name
  policy_arn = aws_iam_policy.get_invoice_summary_lambda_policy.arn
}
