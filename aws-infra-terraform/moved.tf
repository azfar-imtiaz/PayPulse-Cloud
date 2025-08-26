# Handle moved IAM resources from root to module
moved {
  from = aws_iam_group.wallenstam_group
  to   = module.iam.aws_iam_group.wallenstam_group
}

moved {
  from = aws_iam_user.wallenstam_user
  to   = module.iam.aws_iam_user.wallenstam_user
}

moved {
  from = aws_iam_user_group_membership.wallenstam_membership
  to   = module.iam.aws_iam_user_group_membership.wallenstam_membership
}

moved {
  from = aws_iam_policy.autoscaling_permissions
  to   = module.iam.aws_iam_policy.autoscaling_permissions
}

moved {
  from = aws_iam_user_policy_attachment.user_autoscaling_attach
  to   = module.iam.aws_iam_user_policy_attachment.user_autoscaling_attach
}

moved {
  from = aws_iam_policy.api_gateway_policy
  to   = module.iam.aws_iam_policy.api_gateway_policy
}

moved {
  from = aws_iam_user_policy_attachment.attach_api_gateway_policy
  to   = module.iam.aws_iam_user_policy_attachment.attach_api_gateway_policy
}

moved {
  from = aws_iam_role.wallenstam_app_identity_role
  to   = module.iam.aws_iam_role.wallenstam_app_identity_role
}

moved {
  from = aws_iam_role_policy_attachment.attach_dynamodb_readonly
  to   = module.iam.aws_iam_role_policy_attachment.attach_dynamodb_readonly
}

moved {
  from = aws_iam_role.wallenstam_lambda_role
  to   = module.iam.aws_iam_role.wallenstam_lambda_role
}

# Lambda-specific IAM resources
moved {
  from = aws_iam_role.signup_lambda_role
  to   = module.iam.aws_iam_role.signup_lambda_role
}

moved {
  from = aws_iam_policy.signup_lambda_policy
  to   = module.iam.aws_iam_policy.signup_lambda_policy
}

moved {
  from = aws_iam_role_policy_attachment.signup_lambda_role_attachment
  to   = module.iam.aws_iam_role_policy_attachment.signup_lambda_role_attachment
}

moved {
  from = aws_iam_role.login_lambda_role
  to   = module.iam.aws_iam_role.login_lambda_role
}

moved {
  from = aws_iam_policy.login_lambda_policy
  to   = module.iam.aws_iam_policy.login_lambda_policy
}

moved {
  from = aws_iam_role_policy_attachment.login_lambda_role_attachment
  to   = module.iam.aws_iam_role_policy_attachment.login_lambda_role_attachment
}

moved {
  from = aws_iam_role.delete_user_lambda_role
  to   = module.iam.aws_iam_role.delete_user_lambda_role
}

moved {
  from = aws_iam_policy.delete_user_lambda_policy
  to   = module.iam.aws_iam_policy.delete_user_lambda_policy
}

moved {
  from = aws_iam_role_policy_attachment.delete_user_lambda_basic_execution
  to   = module.iam.aws_iam_role_policy_attachment.delete_user_lambda_basic_execution
}

moved {
  from = aws_iam_role_policy_attachment.delete_user_lambda_role_attachment
  to   = module.iam.aws_iam_role_policy_attachment.delete_user_lambda_role_attachment
}

moved {
  from = aws_iam_role.get_rental_invoices_lambda_role
  to   = module.iam.aws_iam_role.get_rental_invoices_lambda_role
}

moved {
  from = aws_iam_policy.get_rental_invoices_lambda_policy
  to   = module.iam.aws_iam_policy.get_rental_invoices_lambda_policy
}

moved {
  from = aws_iam_role_policy_attachment.get_rental_invoices_lambda_basic_execution
  to   = module.iam.aws_iam_role_policy_attachment.get_rental_invoices_lambda_basic_execution
}

moved {
  from = aws_iam_role_policy_attachment.get_rental_invoices_lambda_role_attachment
  to   = module.iam.aws_iam_role_policy_attachment.get_rental_invoices_lambda_role_attachment
}

moved {
  from = aws_iam_role.get_rental_invoice_lambda_role
  to   = module.iam.aws_iam_role.get_rental_invoice_lambda_role
}

moved {
  from = aws_iam_policy.get_rental_invoice_lambda_policy
  to   = module.iam.aws_iam_policy.get_rental_invoice_lambda_policy
}

moved {
  from = aws_iam_role_policy_attachment.get_rental_invoice_lambda_basic_execution
  to   = module.iam.aws_iam_role_policy_attachment.get_rental_invoice_lambda_basic_execution
}

moved {
  from = aws_iam_role_policy_attachment.get_rental_invoice_lambda_role_attachment
  to   = module.iam.aws_iam_role_policy_attachment.get_rental_invoice_lambda_role_attachment
}

moved {
  from = aws_iam_role.get_user_profile_lambda_role
  to   = module.iam.aws_iam_role.get_user_profile_lambda_role
}

moved {
  from = aws_iam_policy.get_user_profile_lambda_policy
  to   = module.iam.aws_iam_policy.get_user_profile_lambda_policy
}

moved {
  from = aws_iam_role_policy_attachment.get_user_profile_lambda_basic_execution
  to   = module.iam.aws_iam_role_policy_attachment.get_user_profile_lambda_basic_execution
}

moved {
  from = aws_iam_role_policy_attachment.get_user_profile_lambda_role_attachment
  to   = module.iam.aws_iam_role_policy_attachment.get_user_profile_lambda_role_attachment
}

# Group policy attachments
moved {
  from = aws_iam_group_policy_attachment.wallenstam_group_policies["arn:aws:iam::aws:policy/AmazonCognitoPowerUser"]
  to   = module.iam.aws_iam_group_policy_attachment.wallenstam_group_policies["arn:aws:iam::aws:policy/AmazonCognitoPowerUser"]
}

moved {
  from = aws_iam_group_policy_attachment.wallenstam_group_policies["arn:aws:iam::aws:policy/AmazonDynamoDBFullAccess"]
  to   = module.iam.aws_iam_group_policy_attachment.wallenstam_group_policies["arn:aws:iam::aws:policy/AmazonDynamoDBFullAccess"]
}

moved {
  from = aws_iam_group_policy_attachment.wallenstam_group_policies["arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryFullAccess"]
  to   = module.iam.aws_iam_group_policy_attachment.wallenstam_group_policies["arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryFullAccess"]
}

moved {
  from = aws_iam_group_policy_attachment.wallenstam_group_policies["arn:aws:iam::aws:policy/AmazonS3FullAccess"]
  to   = module.iam.aws_iam_group_policy_attachment.wallenstam_group_policies["arn:aws:iam::aws:policy/AmazonS3FullAccess"]
}

moved {
  from = aws_iam_group_policy_attachment.wallenstam_group_policies["arn:aws:iam::aws:policy/AmazonSNSFullAccess"]
  to   = module.iam.aws_iam_group_policy_attachment.wallenstam_group_policies["arn:aws:iam::aws:policy/AmazonSNSFullAccess"]
}

moved {
  from = aws_iam_group_policy_attachment.wallenstam_group_policies["arn:aws:iam::aws:policy/AWSLambda_FullAccess"]
  to   = module.iam.aws_iam_group_policy_attachment.wallenstam_group_policies["arn:aws:iam::aws:policy/AWSLambda_FullAccess"]
}

moved {
  from = aws_iam_group_policy_attachment.wallenstam_group_policies["arn:aws:iam::aws:policy/CloudWatchEventsFullAccess"]
  to   = module.iam.aws_iam_group_policy_attachment.wallenstam_group_policies["arn:aws:iam::aws:policy/CloudWatchEventsFullAccess"]
}

moved {
  from = aws_iam_group_policy_attachment.wallenstam_group_policies["arn:aws:iam::aws:policy/CloudWatchLogsFullAccess"]
  to   = module.iam.aws_iam_group_policy_attachment.wallenstam_group_policies["arn:aws:iam::aws:policy/CloudWatchLogsFullAccess"]
}

moved {
  from = aws_iam_group_policy_attachment.wallenstam_group_policies["arn:aws:iam::aws:policy/IAMFullAccess"]
  to   = module.iam.aws_iam_group_policy_attachment.wallenstam_group_policies["arn:aws:iam::aws:policy/IAMFullAccess"]
}

moved {
  from = aws_iam_group_policy_attachment.wallenstam_group_policies["arn:aws:iam::aws:policy/SecretsManagerReadWrite"]
  to   = module.iam.aws_iam_group_policy_attachment.wallenstam_group_policies["arn:aws:iam::aws:policy/SecretsManagerReadWrite"]
}

# Lambda role policy attachments
moved {
  from = aws_iam_role_policy_attachment.lambda_role_policies["arn:aws:iam::aws:policy/AmazonDynamoDBFullAccess"]
  to   = module.iam.aws_iam_role_policy_attachment.lambda_role_policies["arn:aws:iam::aws:policy/AmazonDynamoDBFullAccess"]
}

moved {
  from = aws_iam_role_policy_attachment.lambda_role_policies["arn:aws:iam::aws:policy/AmazonS3FullAccess"]
  to   = module.iam.aws_iam_role_policy_attachment.lambda_role_policies["arn:aws:iam::aws:policy/AmazonS3FullAccess"]
}

moved {
  from = aws_iam_role_policy_attachment.lambda_role_policies["arn:aws:iam::aws:policy/AmazonSNSFullAccess"]
  to   = module.iam.aws_iam_role_policy_attachment.lambda_role_policies["arn:aws:iam::aws:policy/AmazonSNSFullAccess"]
}

moved {
  from = aws_iam_role_policy_attachment.lambda_role_policies["arn:aws:iam::aws:policy/CloudWatchLogsFullAccess"]
  to   = module.iam.aws_iam_role_policy_attachment.lambda_role_policies["arn:aws:iam::aws:policy/CloudWatchLogsFullAccess"]
}

moved {
  from = aws_iam_role_policy_attachment.lambda_role_policies["arn:aws:iam::aws:policy/SecretsManagerReadWrite"]
  to   = module.iam.aws_iam_role_policy_attachment.lambda_role_policies["arn:aws:iam::aws:policy/SecretsManagerReadWrite"]
}

# Lambda resources moved to lambdas module
moved {
  from = data.aws_caller_identity.current
  to   = module.lambdas.data.aws_caller_identity.current
}

moved {
  from = data.aws_s3_bucket_object.fetch_invoices_zip
  to   = module.lambdas.data.aws_s3_bucket_object.fetch_invoices_zip
}

moved {
  from = data.aws_s3_bucket_object.fetch_latest_invoice_zip
  to   = module.lambdas.data.aws_s3_bucket_object.fetch_latest_invoice_zip
}

moved {
  from = data.aws_s3_bucket_object.send_invoice_notification_zip
  to   = module.lambdas.data.aws_s3_bucket_object.send_invoice_notification_zip
}

moved {
  from = data.aws_s3_bucket_object.signup_user_zip
  to   = module.lambdas.data.aws_s3_bucket_object.signup_user_zip
}

moved {
  from = data.aws_s3_bucket_object.login_user_zip
  to   = module.lambdas.data.aws_s3_bucket_object.login_user_zip
}

moved {
  from = data.aws_s3_bucket_object.delete_user_zip
  to   = module.lambdas.data.aws_s3_bucket_object.delete_user_zip
}

moved {
  from = data.aws_s3_bucket_object.get_rental_invoices_zip
  to   = module.lambdas.data.aws_s3_bucket_object.get_rental_invoices_zip
}

moved {
  from = data.aws_s3_bucket_object.get_rental_invoice_zip
  to   = module.lambdas.data.aws_s3_bucket_object.get_rental_invoice_zip
}

moved {
  from = data.aws_s3_bucket_object.get_user_profile_zip
  to   = module.lambdas.data.aws_s3_bucket_object.get_user_profile_zip
}

# Lambda functions
moved {
  from = aws_lambda_function.fetch_invoices
  to   = module.lambdas.aws_lambda_function.fetch_invoices
}

moved {
  from = aws_lambda_function.fetch_latest_invoice
  to   = module.lambdas.aws_lambda_function.fetch_latest_invoice
}

moved {
  from = aws_lambda_function.parse_invoice
  to   = module.lambdas.aws_lambda_function.parse_invoice
}

moved {
  from = aws_lambda_function.send_invoice_notification
  to   = module.lambdas.aws_lambda_function.send_invoice_notification
}

moved {
  from = aws_lambda_function.signup_user
  to   = module.lambdas.aws_lambda_function.signup_user
}

moved {
  from = aws_lambda_function.login_user
  to   = module.lambdas.aws_lambda_function.login_user
}

moved {
  from = aws_lambda_function.delete_user
  to   = module.lambdas.aws_lambda_function.delete_user
}

moved {
  from = aws_lambda_function.get_rental_invoices
  to   = module.lambdas.aws_lambda_function.get_rental_invoices
}

moved {
  from = aws_lambda_function.get_rental_invoice
  to   = module.lambdas.aws_lambda_function.get_rental_invoice
}

moved {
  from = aws_lambda_function.get_user_profile
  to   = module.lambdas.aws_lambda_function.get_user_profile
}

# Lambda permissions
moved {
  from = aws_lambda_permission.fetch_latest_invoice_event
  to   = module.lambdas.aws_lambda_permission.fetch_latest_invoice_event
}

moved {
  from = aws_lambda_permission.allow_s3_invoke_parse_invoice
  to   = module.lambdas.aws_lambda_permission.allow_s3_invoke_parse_invoice
}

# Lambda layers and data sources
moved {
  from = data.klayers_package_latest_version.bcrypt
  to   = module.lambdas.data.klayers_package_latest_version.bcrypt
}

moved {
  from = aws_lambda_layer_version.utils_layer
  to   = module.lambdas.aws_lambda_layer_version.utils_layer
}

moved {
  from = aws_lambda_layer_version.pyjwt_layer
  to   = module.lambdas.aws_lambda_layer_version.pyjwt_layer
}