resource "aws_iam_role" "outlook_oauth_callback_lambda_role" {
  name = "Outlook-OAuth-Callback-Lambda-Role"

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

# No custom policy needed - this Lambda only relays query params into a 302 redirect,
# it touches no AWS resources beyond CloudWatch logs.
resource "aws_iam_role_policy_attachment" "outlook_oauth_callback_lambda_basic_execution" {
  role       = aws_iam_role.outlook_oauth_callback_lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}
