# Wallenstam Invoices table

resource "aws_dynamodb_table" "rental_invoices" {
  name           = var.invoices_table
  billing_mode   = "PROVISIONED"
  read_capacity  = 5
  write_capacity = 5

  hash_key  = var.invoices_table_hash_key
  range_key = var.invoices_table_range_key

  attribute {
    name = var.invoices_table_hash_key
    type = "S"
  }

  attribute {
    name = var.invoices_table_range_key
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

# Users table

resource "aws_dynamodb_table" "users" {
  name         = var.users_table
  billing_mode = "PAY_PER_REQUEST"

  hash_key = var.users_table_hash_key

  attribute {
    name = var.users_table_hash_key
    type = "S"
  }

  attribute {
    name = "Email"
    type = "S"
  }

  # GSI

  global_secondary_index {
    hash_key        = "Email"
    name            = "Email-index"
    projection_type = "ALL"
  }

  tags = {
    Environment = "production"
  }
}

# ============================================================================
# RETAIL INVOICES TABLES
# ============================================================================

# Retail Invoices Base table

resource "aws_dynamodb_table" "retail_invoices" {
  name         = var.retail_invoices_table
  billing_mode = "PAY_PER_REQUEST"

  hash_key  = "UserID"
  range_key = "InvoiceID"

  attribute {
    name = "UserID"
    type = "S"
  }

  attribute {
    name = "InvoiceID"
    type = "S"
  }

  attribute {
    name = "invoice_date"
    type = "S"
  }

  attribute {
    name = "UserID_SubType"
    type = "S"
  }

  # GSI-1: For date-based queries
  global_secondary_index {
    name            = "invoice_date-index"
    hash_key        = "UserID"
    range_key       = "invoice_date"
    projection_type = "ALL"
  }

  # GSI-2: For category + date queries (optimized for "get all invoices by category")
  global_secondary_index {
    name            = "sub_type-invoice_date-index"
    hash_key        = "UserID_SubType"
    range_key       = "invoice_date"
    projection_type = "ALL"
  }

  stream_enabled   = true
  stream_view_type = "NEW_AND_OLD_IMAGES"

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true
  }

  tags = {
    Environment = "production"
  }
}

# Food Delivery Invoices Detail table

resource "aws_dynamodb_table" "food_delivery_invoices" {
  name         = var.food_delivery_invoices_table
  billing_mode = "PAY_PER_REQUEST"

  hash_key = "InvoiceID"

  attribute {
    name = "InvoiceID"
    type = "S"
  }

  server_side_encryption {
    enabled = true
  }

  tags = {
    Environment = "production"
  }
}

# Clothing Invoices Detail table

resource "aws_dynamodb_table" "clothing_invoices" {
  name         = var.clothing_invoices_table
  billing_mode = "PAY_PER_REQUEST"

  hash_key = "InvoiceID"

  attribute {
    name = "InvoiceID"
    type = "S"
  }

  server_side_encryption {
    enabled = true
  }

  tags = {
    Environment = "production"
  }
}

# Technology Invoices Detail table

resource "aws_dynamodb_table" "technology_invoices" {
  name         = var.technology_invoices_table
  billing_mode = "PAY_PER_REQUEST"

  hash_key = "InvoiceID"

  attribute {
    name = "InvoiceID"
    type = "S"
  }

  server_side_encryption {
    enabled = true
  }

  tags = {
    Environment = "production"
  }
}

# Subscription Invoices Detail table

resource "aws_dynamodb_table" "subscription_invoices" {
  name         = var.subscription_invoices_table
  billing_mode = "PAY_PER_REQUEST"

  hash_key = "InvoiceID"

  attribute {
    name = "InvoiceID"
    type = "S"
  }

  server_side_encryption {
    enabled = true
  }

  tags = {
    Environment = "production"
  }
}

# Grocery Invoices Detail table

resource "aws_dynamodb_table" "grocery_invoices" {
  name         = var.grocery_invoices_table
  billing_mode = "PAY_PER_REQUEST"

  hash_key = "InvoiceID"

  attribute {
    name = "InvoiceID"
    type = "S"
  }

  server_side_encryption {
    enabled = true
  }

  tags = {
    Environment = "production"
  }
}

# Miscellaneous Utility Invoices Detail table

resource "aws_dynamodb_table" "misc_utility_invoices" {
  name         = var.misc_utility_invoices_table
  billing_mode = "PAY_PER_REQUEST"

  hash_key = "InvoiceID"

  attribute {
    name = "InvoiceID"
    type = "S"
  }

  server_side_encryption {
    enabled = true
  }

  tags = {
    Environment = "production"
  }
}

# Miscellaneous Invoices Detail table

resource "aws_dynamodb_table" "misc_invoices" {
  name         = var.misc_invoices_table
  billing_mode = "PAY_PER_REQUEST"

  hash_key = "InvoiceID"

  attribute {
    name = "InvoiceID"
    type = "S"
  }

  server_side_encryption {
    enabled = true
  }

  tags = {
    Environment = "production"
  }
}

# Travel Invoices Detail table

resource "aws_dynamodb_table" "travel_invoices" {
  name         = var.travel_invoices_table
  billing_mode = "PAY_PER_REQUEST"

  hash_key = "InvoiceID"

  attribute {
    name = "InvoiceID"
    type = "S"
  }

  server_side_encryption {
    enabled = true
  }

  tags = {
    Environment = "production"
  }
}

# Vendor Configuration table

resource "aws_dynamodb_table" "vendor_config" {
  name         = var.vendor_config_table
  billing_mode = "PAY_PER_REQUEST"

  hash_key = "vendor_id"

  attribute {
    name = "vendor_id"
    type = "S"
  }

  server_side_encryption {
    enabled = true
  }

  tags = {
    Environment = "production"
  }
}
