# ============================================================================
# API GATEWAY CONFIGURATION
# ============================================================================

# Create the API Gateway HTTP API
resource "aws_apigatewayv2_api" "paypulse_api" {
  name          = "PayPulseAPI"
  protocol_type = "HTTP"
}

# API Gateway stage configuration (applies to ALL endpoints)
resource "aws_apigatewayv2_stage" "api_stage" {
  api_id      = aws_apigatewayv2_api.paypulse_api.id
  name        = "$default"
  auto_deploy = true

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api_gateway_logs.arn
    format = jsonencode({
      requestId               = "$context.requestId"
      sourceIp                = "$context.identity.sourceIp"
      requestTime             = "$context.requestTime"
      httpMethod              = "$context.httpMethod"
      path                    = "$context.path"
      status                  = "$context.status"
      protocol                = "$context.protocol"
      responseLength          = "$context.responseLength"
      integrationErrorMessage = "$context.integrationErrorMessage"
    })
  }

  default_route_settings {
    detailed_metrics_enabled = true
    logging_level            = "INFO"
    data_trace_enabled       = true

    # throttling settings
    throttling_burst_limit = 5000   # max concurrent requests in a burst
    throttling_rate_limit  = 1000.0 # average requests per second
  }
}

# CloudWatch log group for API Gateway logging
resource "aws_cloudwatch_log_group" "api_gateway_logs" {
  name = "/aws/apigateway/${aws_apigatewayv2_api.paypulse_api.name}"
  retention_in_days = 30
}

# ============================================================================
# API ENDPOINT CONFIGURATIONS
# Each endpoint requires: integration, route, and lambda permission
# ============================================================================

# --- Endpoint for signup ---

# Connect API Gateway to SignupUser lambda function
resource "aws_apigatewayv2_integration" "signup_integration" {
  api_id                 = aws_apigatewayv2_api.paypulse_api.id
  integration_type       = "AWS_PROXY"  # this means just forward the whole request body to the lambda function
  integration_uri        = module.lambdas.signup_user_invoke_arn
  integration_method     = "POST"
  payload_format_version = "2.0"
}

# Create a route (URL path/auth/signup)
resource "aws_apigatewayv2_route" "signup_route" {
  api_id     = aws_apigatewayv2_api.paypulse_api.id
  route_key  = "POST /${var.api_version}/auth/signup"
  target     = "integrations/${aws_apigatewayv2_integration.signup_integration.id}"
}

# Allow API Gateway to invoke the signup lambda function
resource "aws_lambda_permission" "signup_api_permission" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = module.lambdas.signup_user_function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.paypulse_api.execution_arn}/*/*"
}

# --- Endpoint for login ---

# Connect API Gateway to LoginUser lambda function
resource "aws_apigatewayv2_integration" "login_integration" {
  api_id                 = aws_apigatewayv2_api.paypulse_api.id
  integration_type       = "AWS_PROXY"  # this means just forward the whole request body to the lambda function
  integration_uri        = module.lambdas.login_user_invoke_arn
  integration_method     = "POST"
  payload_format_version = "2.0"
}

# Create a route (URL path/auth/login)
resource "aws_apigatewayv2_route" "login_route" {
  api_id    = aws_apigatewayv2_api.paypulse_api.id
  route_key = "POST /${var.api_version}/auth/login"
  target    = "integrations/${aws_apigatewayv2_integration.login_integration.id}"
}


# Allow API Gateway to invoke the login lambda function
resource "aws_lambda_permission" "login_api_permission" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = module.lambdas.login_user_function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.paypulse_api.execution_arn}/*/*"
}

# --- Endpoint for fetch_invoices ---

# Connect API Gateway to fetch_invoices lambda function
resource "aws_apigatewayv2_integration" "fetch_invoices_integration" {
  api_id                 = aws_apigatewayv2_api.paypulse_api.id
  integration_type       = "AWS_PROXY"  # this means just forward the whole request body to the lambda function
  integration_uri        = module.lambdas.fetch_invoices_invoke_arn
  integration_method     = "POST"
  payload_format_version = "2.0"
}

# Create a route (URL path/user/fetch_invoices)
resource "aws_apigatewayv2_route" "fetch_invoices_route" {
  api_id    = aws_apigatewayv2_api.paypulse_api.id
  route_key = "POST /${var.api_version}/invoices/{type}/ingest"
  target    = "integrations/${aws_apigatewayv2_integration.fetch_invoices_integration.id}"
}

# Allow API Gateway to invoke the fetch_invoices lambda function
resource "aws_lambda_permission" "fetch_invoices_api_permission" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = module.lambdas.fetch_invoices_function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.paypulse_api.execution_arn}/*/*"
}

# --- Endpoint for fetch_latest_invoice ---

# Connect API Gateway to fetch_invoices lambda function
resource "aws_apigatewayv2_integration" "fetch_latest_invoice_integration" {
  api_id                 = aws_apigatewayv2_api.paypulse_api.id
  integration_type       = "AWS_PROXY"  # this means just forward the whole request body to the lambda function
  integration_uri        = module.lambdas.fetch_latest_invoice_invoke_arn
  integration_method     = "POST"
  payload_format_version = "2.0"
}

# Create a route (URL path/user/fetch_latest_invoice)
resource "aws_apigatewayv2_route" "fetch_latest_invoice_route" {
  api_id    = aws_apigatewayv2_api.paypulse_api.id
  route_key = "POST /${var.api_version}/invoices/{type}/ingest/latest"
  target    = "integrations/${aws_apigatewayv2_integration.fetch_latest_invoice_integration.id}"
}

# Allow API Gateway to invoke the fetch_latest_invoice lambda function
resource "aws_lambda_permission" "fetch_latest_invoice_api_permission" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = module.lambdas.fetch_latest_invoice_function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.paypulse_api.execution_arn}/*/*"
}

# --- Endpoint for delete_user ---

# Connect APIGateway to delete_user lambda function
resource "aws_apigatewayv2_integration" "delete_user_integration" {
  api_id                 = aws_apigatewayv2_api.paypulse_api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = module.lambdas.delete_user_invoke_arn
  integration_method     = "POST"
  payload_format_version = "2.0"
}

# Create a route (URL path/user/delete)
resource "aws_apigatewayv2_route" "delete_user_route" {
  api_id    = aws_apigatewayv2_api.paypulse_api.id
  route_key = "DELETE /${var.api_version}/user/me"
  target    = "integrations/${aws_apigatewayv2_integration.delete_user_integration.id}"
}

# Allow APIGateway to invoke the delete_user lambda function
resource "aws_lambda_permission" "delete_user_api_permission" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = module.lambdas.delete_user_function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.paypulse_api.execution_arn}/*/*"
}

# --- Endpoint for get_rental_invoices ---

# Connect APIGateway to get_rental_invoices lambda function
resource "aws_apigatewayv2_integration" "get_rental_invoices_integration" {
  api_id                 = aws_apigatewayv2_api.paypulse_api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = module.lambdas.get_rental_invoices_invoke_arn
  integration_method     = "POST"
  payload_format_version = "2.0"
}

# Create a route (URL path/user/get_rental_invoices)
resource "aws_apigatewayv2_route" "get_rental_invoices_route" {
  api_id    = aws_apigatewayv2_api.paypulse_api.id
  route_key = "GET /${var.api_version}/invoices/{type}"
  target    = "integrations/${aws_apigatewayv2_integration.get_rental_invoices_integration.id}"
}

# Allow APIGateway to invoke the get_rental_invoices lambda function
resource "aws_lambda_permission" "get_rental_invoices_api_permission" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = module.lambdas.get_rental_invoices_function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.paypulse_api.execution_arn}/*/*"
}

# --- Endpoint for get_rental_invoice ---

# Connect APIGateway to get_rental_invoice lambda function
resource "aws_apigatewayv2_integration" "get_rental_invoice_integration" {
  api_id                 = aws_apigatewayv2_api.paypulse_api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = module.lambdas.get_rental_invoice_invoke_arn
  integration_method     = "POST"
  payload_format_version = "2.0"
}

# Create a route (URL path/user/get_rental_invoice)
resource "aws_apigatewayv2_route" "get_rental_invoice_route" {
  api_id    = aws_apigatewayv2_api.paypulse_api.id
  route_key = "GET /${var.api_version}/invoices/{type}/{invoice_id}"
  target    = "integrations/${aws_apigatewayv2_integration.get_rental_invoice_integration.id}"
}

# Allow APIGateway to invoke the get_rental_invoice lambda function
resource "aws_lambda_permission" "get_rental_invoice_api_permission" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = module.lambdas.get_rental_invoice_function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.paypulse_api.execution_arn}/*/*"
}

# --- Endpoint for get_user_profile ---

# Connect APIGateway to get_user_profile lambda function
resource "aws_apigatewayv2_integration" "get_user_profile_integration" {
  api_id                 = aws_apigatewayv2_api.paypulse_api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = module.lambdas.get_user_profile_invoke_arn
  integration_method     = "POST"
  payload_format_version = "2.0"
}

# Create a route (URL path/user/me)
resource "aws_apigatewayv2_route" "get_user_profile_route" {
  api_id    = aws_apigatewayv2_api.paypulse_api.id
  route_key = "GET /${var.api_version}/user/me"
  target    = "integrations/${aws_apigatewayv2_integration.get_user_profile_integration.id}"
}

# Allow APIGateway to invoke the get_user_profile lambda function
resource "aws_lambda_permission" "get_user_profile_api_permission" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = module.lambdas.get_user_profile_function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.paypulse_api.execution_arn}/*/*"
}