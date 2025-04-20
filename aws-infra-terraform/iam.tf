# === Defining the user group ===
resource "aws_iam_group" "wallenstam_group" {
  name = var.iam_user_group
}

# attach AWS managed policies to the group
resource "aws_iam_group_policy_attachment" "wallenstam_group_policies" {
  for_each = toset([
    "arn:aws:iam::aws:policy/AmazonCognitoPowerUser",
    "arn:aws:iam::aws:policy/AmazonDynamoDBFullAccess",
    "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryFullAccess",
    "arn:aws:iam::aws:policy/AmazonS3FullAccess",
    "arn:aws:iam::aws:policy/AmazonSNSFullAccess",
    "arn:aws:iam::aws:policy/AWSLambda_FullAccess",
    "arn:aws:iam::aws:policy/CloudWatchEventsFullAccess",
    "arn:aws:iam::aws:policy/CloudWatchLogsFullAccess",
    "arn:aws:iam::aws:policy/IAMFullAccess",
    "arn:aws:iam::aws:policy/SecretsManagerReadWrite"
	])

  group      = aws_iam_group.wallenstam_group.name
  policy_arn = each.value
}

# === Defining the user and assigning them to the "Wallenstam" user group ===
resource "aws_iam_user" "wallenstam_user" {
  name = var.iam_user
}

resource "aws_iam_user_group_membership" "wallenstam_membership" {
  user = aws_iam_user.wallenstam_user.name
  groups = [
    aws_iam_group.wallenstam_group.name
  ]
}

# === Defining the autoscaling policy ===
resource "aws_iam_policy" "autoscaling_permissions" {
  name = "TerraformAutoScalingPermissions"
  description = "Permissions required by Terraform to manage DynamoDB autoscaling"
  policy      = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = [
          "application-autoscaling:DescribeScalableTargets",
          "application-autoscaling:DescribeScalingPolicies",
          "application-autoscaling:DescribeScheduledActions",
          "application-autoscaling:ListTagsForResource"
        ]
        Resource = "*"
      }
    ]
  })
}


# attach the autoscaling policy to the wallenstam_user
# NOTE: This is not the best way to do this. Policies should be attached to the user group that the user is part of. However, the wallenstam_group already has the maximum amount of policies attached to it (10)
resource "aws_iam_user_policy_attachment" "user_autoscaling_attach" {
  policy_arn = aws_iam_policy.autoscaling_permissions.arn
  user       = aws_iam_user.wallenstam_user.name
}


# === Defining the roles ===

# ROLE 1: The app identity role

resource "aws_iam_role" "wallenstam_app_identity_role" {
  # this role has three policies: AmazonDynamoDBReadOnlyAccess, Cognito-unauthenticated, and WallenstamSNSPolicy
  name = var.app_identity_role
  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Principal = {
          Federated = "cognito-identity.amazonaws.com"
        },
        Action = "sts:AssumeRoleWithWebIdentity",
        Condition = {
          "StringEquals" = {
            "cognito-identity.amazonaws.com:aud" = "eu-west-1:81322675-4a0a-4b9b-a406-0058e1e2d9f4"
          },
          "ForAnyValue:StringLike" = {
            "cognito-identity.amazonaws.com:amr" = "unauthenticated"
          }
        }
      }
    ]
  })

  # inline policy for Cognito-unauthenticated
  inline_policy {
    name = "cognito-unauthenticated"
    policy = jsonencode({
      "Version": "2012-10-17",
      "Statement": [
        {
          "Effect": "Allow",
          "Action": [
              "cognito-identity:GetCredentialsForIdentity"
          ],
          "Resource": ["*"]
        }
      ]
    })
  }

  # inline policy for WallenstamSNSPolicy
  inline_policy {
    name = "wallenstam_sns_policy"
    policy = jsonencode({
      "Version": "2012-10-17",
      "Statement": [
          {
              "Sid": "VisualEditor0",
              "Effect": "Allow",
              "Action": "sns:CreatePlatformEndpoint",
              "Resource": "*"
          }
      ]
    })
  }
}

# attach the AmazonDynamoDBReadOnlyAccess managed policy to the wallenstam_app_identity_role
resource "aws_iam_role_policy_attachment" "attach_dynamodb_readonly" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonDynamoDBReadOnlyAccess"
  role       = aws_iam_role.wallenstam_app_identity_role.name
}

# ROLE 2: AWSServiceRoleForApplicationAutoScaling_DynamoDBTable

#   This is an AWS-managed role, I am just mentioning it here
#   It's important that this block remains commented out, since we don't need to define an AWS managed role. Doing so will create an error state
#   apparently, we don't even need to import this role... Terraform will create it itself when creating a service that uses this role

/*
resource "aws_iam_role" "dynamodb_autoscale_role" {
  name = "AWSServiceRoleForApplicationAutoScaling_DynamoDBTable"
  assume_role_policy = jsonencode({
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Principal": {
          "Service": "dynamodb.application-autoscaling.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }]
  })
}
*/

# ROLE 3: Wallenstam-Lambda-Role
resource "aws_iam_role" "wallenstam_lambda_role" {
  name = var.lambda_role
  assume_role_policy = jsonencode({
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Principal": {
          "Service": "lambda.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
      }]
  })
}

# attach existing managed policies to this role
resource "aws_iam_role_policy_attachment" "lambda_role_policies" {
  for_each = toset([
    "arn:aws:iam::aws:policy/AmazonDynamoDBFullAccess",
    "arn:aws:iam::aws:policy/AmazonS3FullAccess",
    "arn:aws:iam::aws:policy/AmazonSNSFullAccess",
    # "arn:aws:iam::aws:policy/AmazonTextractFullAccess",
    "arn:aws:iam::aws:policy/CloudWatchLogsFullAccess",
    "arn:aws:iam::aws:policy/SecretsManagerReadWrite"
  ])

  role       = aws_iam_role.wallenstam_lambda_role.name
  policy_arn = each.value
}