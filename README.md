# PayPulse-Cloud
This repository contains the Cloud backend for the PayPulse app. The backend for this app is developed in AWS and maintained using Terraform.

PayPulse is an iOS app that fetches invoices from a Gmail inbox, parses them, and presents invoice information and statistics. 
The GitHub link to the PayPulse app can be found [here](https://github.com/azfar-imtiaz/PayPulse).

## Project Structure
```
.
├── lambdas
│   ├── fetch_invoices	
│       ├── lambda_function.py
│       ├── requirements.txt
│   ├── fetch_latest_invoice
│       ├── main.py
│       ├── requirements.txt
│   ├── parse_invoice
│       ├── src
│           ├── HyresaviParser.py
│           ├── lambda_function.py
│           ├── logging_config.py
│       ├── Dockerfile
│       ├── event.json
│       ├── requirements.txt
│   ├── send_invoice_notification
│       ├── main.py
│       ├── requirements.txt
├── aws-infra-terraform
│   ├── main.tf			        # Root module definition (minimal)
│   ├── provider.tf			# AWS provider configuration
│   ├── variables.tf		        # Input variables
│   ├── terraform.tfvars		# Private secret values (gitignored)
│   ├── secrets.tf			# AWS Secrets Manager resource
│   ├── iam.tf			        # IAM roles and policies
│   ├── dynamodb.tf			# DynamoDB table and autoscaling config
│   ├── sns.tf                   	# SNS topic for notifications
│   ├── cloudwatch.tf            	# CloudWatch log group definitions
│   ├── cognito.tf               	# Cognito identity pool
│   ├── lambdas.tf               	# Lambda function definitions
│   ├── eventbridge.tf           	# Scheduled EventBridge trigger
│   ├── terraform.tfstate        	# Terraform state file (not in repo)
└── README.md                	 # You're here!
````

## Getting Started

#### Initialize Terraform 

```
terraform init
```

#### Check changes
```
terraform plan
```

#### Apply changes
```
terraform apply
```

## Infrastructure Overview

### S3 Bucket
This infrastructure consists of two S3 buckets:

- **Rental invoices bucket**

This bucket contains the rental invoices that are fetched from the email inbox and uploaded. The path to the invoices is structured like this:
```
rental-invoices-bucket/rental-invoices/username/invoice_0001.pdf
```

Here, the username is structured from the user's email address - the first part of it (just before the `@` in the email address).
So for example, if the email address is `firstName_lastName@gmail.com`, the username would be `firstName_lastName`.

- **Lambda functions bucket**

This bucket is for containing the source code of the following lambda functions:
- Fetch all invoices
- Fetch latest invoice
- Send invoice notification

The source code of these lambda functions is uploaded as zipped files to this bucket. 
Everytime there is a change to any of these functions, a new version of their zipped file will be uploaded to this S3 bucket. 
That's how these lambda functions are deployed.

### Lambda Functions

There are four lambda functions, and apart from `fetch_invoices`(which has a manual trigger), all of them are linked, in a way. The execution of one triggers a chain of events.

| Function | Trigger | Description | Deployment |
| :-------------: | :-------: | ------- | ------- |
| Fetch all invoices  | Manual | This function fetches all rental invoices from the email inbox | Zip upload to S3 bucket |
| Fetch latest invoice | EventBridge (every weekday 8:30 AM) | This function fetches the rental invoice for the current month, if available | Zip upload to S3 bucket |
| Parse invoice | S3 (rental invoice upload) | This function parses a rental invoice and stores the information in DynamoDB | Docker image pushed to ECR repository |
| Send invoice notification | DynamoDB stream | This function sends an email and iOS notification everytime a new rental invoice is parsed | Zip upload to S3 bucket |

1. The `fetch_latest_invoice` function is triggered once every weekday in the morning. It looks for the latest rental invoice, by checking to see if there is a rental invoice available for the current month for which there is not already a corresponding record in the DynamoDB table. If it finds such an invoice, it uploads it to a specific path in the rental invoices S3 bucket. 
2. This triggers the `parse_invoice` function, which downloads this rental invoice, parses the relevant information from it, and uploads it to the DynamoDB table containing the data of parsed invoices.
3. This triggers the `send_invoice_notification` function, which sends a notification to an iOS device and my email address, informing that a new invoice is available. This notification contains the total amount due and the due date.

### Secrets Manager

I am using AWS Secrets Manager for sensitive values, such as email credentials. These values are not present in `secrets.tf` or `variables.tf`.

#### Usage
- Secrets are defined in `secrets.tf`
- Their values are passed via `terraform.tfvars`, which is gitignore'd.

| Secret Name | Purpose |
| ----------- | ------- |
| Email-Access-Credentials  | GMAIL_USER, GMAIL_PASSWORD, GMAIL_IMAP_URL |

### Simple Notification Service (SNS)

I am using SNS for sending notifications to iOS devices and email addresses. 
- **Topic**: NewInvoiceTopicNotification.
- **Subscriptions**: Email + iOS push (these have been set up manually so far).

### DynamoDB

I am using DynamoDB for storing parsed invoice data. So far, I only have a single table that contains the parsed data of rental invoices. 
Later, I plan on expanding the infrastructure by parsing more invoices of different kinds. More tables will be added here then.

#### Tables
**1. Wallenstam-Invoices**
- Partition key: `InvoiceID`
- GSI: `due_date_year-due_date_month-index`
- Stream: New and old images
- Autoscaling enabled (1-10 units, 70% target)

### IAM

- User group: `Wallenstam`
- IAM user: `WallenstamTenant`
- Roles:
    - App identity role: `WallenstamAppIdentityRole`
    - Lambda functions role: `Wallenstam-Lambda-Role`

### Cognito

This is for configuring push notifications for iOS devices.
- Identity Pool: `WallenstamAppIdentityPool`
- Used for unauthenticated gues access (iOS app)

### CloudWatch
I am currently using CloudWatch for monitoring for the lambda functions. Currently, there are four log groups, each corresponding to the equivalent lambda function:
- `/aws/lambda/fetch_invoices`
- `/aws/lambda/fetch_latest_invoice`
- `/aws/lambda/parse_invoice`
- `/aws/lambda/send_invoice_notification`

## Next Steps
- Some IAM policies are currently AWS-managed - migrate them to Terraform-managed
- Move SNS subscription management to Terraform
    - I would like to define a flow where, whenever a new user installs the app and signs up using their Gmail account, they automatically get configured for push notifications. Right now, this process has to be configured manually
- Add CI/CD workflow
    - I would like to set up a flow where, whenever there any updates or additions to the lambda functions are pushed, it triggers a pipeline which tests the function, and then deploys it
    - GitHub Actions can be used for this