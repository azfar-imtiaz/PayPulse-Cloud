resource "aws_iam_role" "delete_retail_invoice_lambda_role" {
  name = "delete_retail_invoice_lambda_role"
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

resource "aws_iam_policy" "delete_retail_invoice_lambda_policy" {
  name = "Delete-Retail-Invoice-Lambda-Policy"
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Action = [
          "dynamodb:Query",
          "dynamodb:DeleteItem"
        ],
        Resource = [
          var.retail_invoices_table_arn,
          var.food_delivery_invoices_table_arn,
          var.clothing_invoices_table_arn,
          var.technology_invoices_table_arn,
          var.subscription_invoices_table_arn,
          var.grocery_invoices_table_arn,
          var.misc_utility_invoices_table_arn,
          var.misc_invoices_table_arn,
          var.travel_invoices_table_arn
        ]
      },
      {
        Effect = "Allow",
        Action = [
          "s3:DeleteObject"
        ],
        Resource = [
          "arn:aws:s3:::${var.invoices_bucket_name}/*"
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "delete_retail_invoice_lambda_basic_execution" {
  role       = aws_iam_role.delete_retail_invoice_lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "delete_retail_invoice_lambda_role_attachment" {
  role       = aws_iam_role.delete_retail_invoice_lambda_role.name
  policy_arn = aws_iam_policy.delete_retail_invoice_lambda_policy.arn
}
