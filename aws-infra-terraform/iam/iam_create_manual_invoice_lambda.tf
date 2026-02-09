resource "aws_iam_role" "create_manual_invoice_lambda_role" {
  name = "create_manual_invoice_lambda_role"
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

resource "aws_iam_policy" "create_manual_invoice_lambda_policy" {
  name = "Create-Manual-Invoice_Lambda_Policy"
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Action = [
          "dynamodb:PutItem"
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
          "secretsmanager:GetSecretValue"
        ],
        Resource = [
          "arn:aws:secretsmanager:${var.aws_region}:*:secret:JWT-Secret*"
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "create_manual_invoice_lambda_basic_execution" {
  role       = aws_iam_role.create_manual_invoice_lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "create_manual_invoice_lambda_role_attachment" {
  role       = aws_iam_role.create_manual_invoice_lambda_role.name
  policy_arn = aws_iam_policy.create_manual_invoice_lambda_policy.arn
}