resource "aws_dynamodb_table" "wallenstam_invoices" {
  name         = var.invoices_table
  billing_mode = "PROVISIONED"

  hash_key = var.invoices_table_hash_key

  attribute {
    name = var.invoices_table_hash_key
    type = "S"
  }
  
  # GSI
  global_secondary_index {
    name            = "${var.invoices_table_due_date_year}-${var.invoices_table_due_date_month}-index"
    hash_key        = var.invoices_table_due_date_year
    range_key       = var.invoices_table_due_date_month
    projection_type = "ALL"
    read_capacity   = 1
    write_capacity  = 1
  }

  attribute {
    name = var.invoices_table_due_date_year
    type = "S"
  }

  attribute {
    name = var.invoices_table_due_date_month
    type = "S"
  }

  stream_enabled   = true
  stream_view_type = "NEW_AND_OLD_IMAGES"

  point_in_time_recovery {
    enabled = false
  }

  server_side_encryption {
    enabled = true
  }
}
