# Daily trigger for fetch_latest_invoice lambda function
resource "aws_cloudwatch_event_rule" "daily_lambda_trigger" {
  name                = var.daily_lambda_trigger
  schedule_expression = var.daily_lambda_trigger_schedule
  is_enabled          = true
}

# DynamoDB trigger event for send_invoice_notification lambda function
resource "aws_lambda_event_source_mapping" "send_invoice_notification_trigger" {
  # event_source_arn  = "arn:aws:dynamodb:${var.aws_region}:${data.aws_caller_identity.current.account_id}:table/${var.invoices_table}/stream/2024-11-15T10:18:19.028"
  event_source_arn = aws_dynamodb_table.rental_invoices.stream_arn
  function_name     = aws_lambda_function.send_invoice_notification.arn
  starting_position = "LATEST"
  batch_size        = 1
  enabled           = true
}