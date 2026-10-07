# IAM Role for start_retail_invoice_backfill Lambda function.
#
# NOTE: this endpoint is untested - see lambdas/invoices/start_retail_invoice_backfill/main.py.

resource "aws_iam_role" "start_retail_invoice_backfill_lambda_role" {
  name = "Start-Retail-Invoice-Backfill_Lambda_Role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Action = "sts:AssumeRole",
        Effect = "Allow",
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_policy" "start_retail_invoice_backfill_lambda_policy" {
  name = "Start-Retail-Invoice-Backfill_Lambda_Policy"

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ],
        Resource = "arn:aws:logs:*:*:*"
      },
      # Only permission this Lambda needs beyond logging - start an execution of the
      # backfill state machine. No DynamoDB/S3/Gmail/Jev/Gemini access at all - all real
      # work happens inside fetch_and_classify_retail_invoices, invoked by Step Functions.
      {
        Effect   = "Allow",
        Action   = ["states:StartExecution"],
        Resource = var.retail_invoice_backfill_state_machine_arn
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "start_retail_invoice_backfill_lambda_policy_attachment" {
  role       = aws_iam_role.start_retail_invoice_backfill_lambda_role.name
  policy_arn = aws_iam_policy.start_retail_invoice_backfill_lambda_policy.arn
}
