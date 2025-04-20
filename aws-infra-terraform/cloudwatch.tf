resource "aws_cloudwatch_log_group" "fetch_invoices" {
  name              = "/aws/lambda/fetch_invoices"
  retention_in_days = 90
}

resource "aws_cloudwatch_log_group" "fetch_latest_invoice" {
  name              = "/aws/lambda/fetch_latest_invoice"
  retention_in_days = 90
}

resource "aws_cloudwatch_log_group" "parse_invoice" {
  name              = "/aws/lambda/parse_invoice"
  retention_in_days = 90
}

resource "aws_cloudwatch_log_group" "send_invoice_notification" {
  name              = "/aws/lambda/send_invoice_notification"
  retention_in_days = 90
}