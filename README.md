# PayPulse-Cloud
This repository contains the Cloud backend for the PayPulse app. The backend for this app is developed in AWS and maintained using Terraform.

PayPulse is an iOS app that fetches invoices from a Gmail inbox, parses them, and presents invoice information and statistics. 
The GitHub link to the PayPulse app can be found [here](https://github.com/azfar-imtiaz/PayPulse).

## Cloud Architecture Diagram
![Cloud architecture](architecture_diagrams/PayPulse-Architecture.drawio.svg)

## Project Structure
```
.
├── lambdas
│   ├── invoices
│       ├── fetch_invoices	
│           ├── lambda_function.py
│           ├── requirements.txt
│       ├── fetch_latest_invoice
│           ├── main.py
│           ├── requirements.txt
│       ├── parse_invoice
│           ├── src
│               ├── HyresaviParser.py
│               ├── lambda_function.py
│               ├── logging_config.py
│           ├── Dockerfile
│           ├── event.json
│           ├── requirements.txt
│       ├── get_rental_invoice
│           ├── main.py
│           ├── requirements.txt
│       ├── get_rental_invoices
│           ├── main.py
│           ├── requirements.txt
│       ├── send_invoice_notification
│           ├── main.py
│           ├── requirements.txt
│   ├── users
│       ├── login_user
│           ├── main.py
│           ├── requirements.txt
│       ├── signup_user
│           ├── main.py
│           ├── requirements.txt
│       ├── get_user_profile
│           ├── main.py
│           ├── requirements.txt
│       ├── delete_user
│           ├── main.py
│           ├── requirements.txt
├── lambda_layers
│   ├── common
│       ├── python
│           ├── utils
│               ├── __init__.py
│               ├── auth_utils.py
│               ├── dynamodb_utils.py
│               ├── jwt_utils.py
│               ├── s3_utils.py
│               ├── secretsmanager_utils.py
│               ├── utility_functions.py
│               ├── error_handling.py
│               ├── responses.py
│               ├── exceptions.py
│   ├── jwt
│       ├── python
│           ├── jwt
│               ├── ... jwt package Python scripts
├── aws-infra-terraform
│   ├── main.tf			            # Root module definition (minimal)
│   ├── provider.tf			    # AWS provider configuration
│   ├── variables.tf		            # Input variables
│   ├── terraform.tfvars		    # Private secret values (gitignored)
│   ├── secrets.tf			    # AWS Secrets Manager resource
│   ├── iam.tf			            # IAM roles and policies
│   ├── iam_signup_lambda.tf	            # IAM role and policy for the sign-up lambda function
│   ├── iam_login_lambda.tf	            # IAM role and policy for the login lambda function
│   ├── iam_delete_user_lambda.tf	    # IAM role and policy for the delete-user lambda function
│   ├── iam_get_rental_invoice_lambda.tf   # IAM role and policy for the get-rental-invoice lambda function
│   ├── iam_get_rental_invoices_lambda.tf   # IAM role and policy for the get-rental-invoices lambda function
│   ├── dynamodb.tf			    # DynamoDB tables
│   ├── dynamodb_autoscaling.tf		    # DynamoDB autoscaling config
│   ├── sns.tf                   	    # SNS topic for notifications
│   ├── cloudwatch.tf            	    # CloudWatch log group definitions
│   ├── cognito.tf               	    # Cognito identity pool
│   ├── lambdas.tf               	    # Lambda function definitions
│   ├── eventbridge.tf           	    # Scheduled EventBridge trigger
│   ├── api_gateway.tf           	    # API Gateway for configuration of all endpoints
│   ├── terraform.tfstate        	    # Terraform state file (not in repo)
└── README.md                	            # You're here!
```

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

#### - Rental invoices bucket

This bucket contains the rental invoices that are fetched from the email inbox and uploaded. The path to the invoices is structured like this:
```
rental-invoices-bucket/rental-invoices/user_id/invoice_0001.pdf
```

Here, the user ID is generated dynamically, which happens when a user signs up. The user ID is a UUID prefixed with `user_`-

#### - Lambda functions bucket

This bucket is for containing the source code of the following lambda functions:
- Ingest all invoices
- Ingest latest invoice
- Send invoice notification
- Get invoice
- Get invoices
- Delete user
- Get user profile
- Login
- Signup

The source code of these lambda functions is uploaded as zipped files to this bucket. 
Everytime there is a change to any of these functions, a new version of their zipped file will be uploaded to this S3 bucket. 
That's how these lambda functions are deployed.

### Lambda Functions

There are several lambda functions, and some of them are linked, in a way. The execution of one triggers a chain of events.

|         Function          |        Function name        | Trigger | Description                                                                                                              | Deployment |
|:-------------------------:|:---------------------------:| :-------: |--------------------------------------------------------------------------------------------------------------------------| ------- |
|           Login           |        `login_user`         | API Gateway | This function allows an existing user to login, and returns an access token                                              | Zip upload to S3 bucket |
|          Sign up          |        `signup_user`        | API Gateway | This function allows a new user to sign up to PayPulse                                                                   | Zip upload to S3 bucket |
|       Get user profile    |     `get_user_profile`      | API Gateway | This function retrieves the user profile information (name, email, created date) for the authenticated user             | Zip upload to S3 bucket |
|    Ingest all invoices    |      `fetch_invoices`       | API Gateway | This function fetches all rental invoices from the email inbox                                                           | Zip upload to S3 bucket |
|   Ingest latest invoice   |   `fetch_latest_invoice`    | EventBridge (every weekday 8:30 AM) | This function fetches the rental invoice for the current month, if available                                             | Zip upload to S3 bucket |
|       Parse invoice       |       `parse_invoice`       | S3 (rental invoice upload) | This function parses a rental invoice and stores the information in DynamoDB                                             | Docker image pushed to ECR repository |
|        Get invoice        |    `get_rental_invoice`     | API Gateway | This function retrieves the full invoice details for a given invoice ID. **This is not being used in the app right now** | Zip upload to S3 bucket |
|       Get invoices        |    `get_rental_invoices`    | API Gateway | This function retrieves and returns all invoices for a logged-in user                                                    | Zip upload to S3 bucket |
|        Delete user        |        `delete_user`        | API Gateway | This function deletes all data for a given user in PayPulse Cloud                                                        | Zip upload to S3 bucket |
| Send invoice notification | `send_invoice_notification` | DynamoDB stream | This function sends an email and iOS notification everytime a new rental invoice is parsed                               | Zip upload to S3 bucket |

1. The `fetch_latest_invoice` function is triggered once every weekday in the morning. It looks for the latest rental invoice, by checking to see if there is a rental invoice available for the current month for which there is not already a corresponding record in the DynamoDB table. If it finds such an invoice, it uploads it to a specific path in the rental invoices S3 bucket. 
2. This triggers the `parse_invoice` function, which downloads this rental invoice, parses the relevant information from it, and uploads it to the DynamoDB table containing the data of parsed invoices.
3. This triggers the `send_invoice_notification` function, which sends a notification to an iOS device and my email address, informing that a new invoice is available. This notification contains the total amount due and the due date.

The other lambda functions are deployed as API endpoints, via API Gateway.

#### Lambda layers

I am using lambda layers for some extended functionalities that are not available out-of-the-box in Python. These are as follows:
- Bcrypt
- JWT
- Common utility functions used across the lambda functions

I am using Klayers for Bcrypt. For the other two, I have created the lambda layers manually (they can be found under the `lambda_layers` directory). These lambda layers are attached to different lambda functions as per requirement in the lambda function Terraform definition.

Everytime there is a change or addition to the common utility functions, I generate a new zip file containing these functions, and then push the change using `terraform apply`.

### API Gateway

The following endpoints are deployed in PayPulseAPI via API Gateway, each of them linked to their corresponding lambda functions:

|       Endpoint       |   Lambda function    |
|:--------------------:|:--------------------:|
|        Login         |      login_user      |
|       Sign up        |     signup_user      |
|   Get user profile   |   get_user_profile   |
|  Fetch all invoices  |    fetch_invoices    |
| Fetch latest invoice | fetch_latest_invoice |
|     Get invoices     | get_rental_invoices  |
| Get invoice details  |  get_rental_invoice  |
|     Delete user      |     delete_user      |

The routes are structured like this:

```
├── /v1
│   ├── /auth
│       ├── /signup
│           ├── POST
│       ├── /login
│           ├── POST
│   ├── /invoices
│       ├── {type}
│               ├── GET
│           ├── {invoice_id}
│               ├── GET
│           ├── /ingest
│               ├── POST
│   ├── /user
│       ├── /me
│           ├── GET
│           ├── DELETE
```

JWT token based authentication has been implemented here. The login call returns an access token, which must be attached to the header of all other API calls (apart from sign-up of course). This allows the lambda function against the API call to retrieve the user ID from the token and perform the operation for that specific user.

### Secrets Manager

I am using AWS Secrets Manager for sensitive values, such as email credentials. These values are not present in `secrets.tf` or `variables.tf`.

#### Usage
- Secrets are defined in `secrets.tf`
- Their values are passed via `terraform.tfvars`, which is gitignore'd.
- When a new user signs up, a secret is automatically created for them in SecretsManager. 

| Secret Name | Purpose |
| ----------- | ------- |
| gmail/user/{user_id}  | GMAIL_USER, GMAIL_PASSWORD, GMAIL_IMAP_URL |

### Simple Notification Service (SNS)

I am using SNS for sending notifications to iOS devices and email addresses. 
- **Topic**: NewInvoiceTopicNotification.
- **Subscriptions**: Email + iOS push (these have been set up manually so far).

### DynamoDB

I am using DynamoDB for storing parsed invoice data, as well as user information. So far, I have two tables for these purposes.
Later, I plan on expanding the infrastructure by parsing more invoices of different kinds. More tables will be added here then.

#### Tables
**1. RentalInvoices**
- Partition key: `InvoiceID`
- GSI: `due_date_year-due_date_month-index`
- Billing mode: Provisioned
- Stream: New and old images
- Autoscaling enabled (1-10 units, 70% target)

**2. Users**
- Partition key: `UserID`
- GSI: `Email-index`
- Billing mode: Pay per request

### IAM

- User group: `Wallenstam`
- IAM user: `WallenstamTenant`
- Roles:
    - App identity role: `WallenstamAppIdentityRole`
    - Lambda functions roles:
        - `Wallenstam-Lambda-Role`
        - `Login-Lambda-Role`
        - `Signup-Lambda-Role`
        - `get_rental_invoices_lambda_role`
        - `delete_user_lambda_role`

### Cognito

This is for configuring push notifications for iOS devices.
- Identity Pool: `WallenstamAppIdentityPool`
- Used for unauthenticated guest access (iOS app)

### CloudWatch
I am currently using CloudWatch for monitoring for the lambda functions. Currently, there are the following log groups, each corresponding to the equivalent lambda function:
- `/aws/apigateway/PayPulseAPI`        # this is for the sign-up lambda function
- `/aws/lambda/login_user`
- `/aws/lambda/fetch_invoices`
- `/aws/lambda/fetch_latest_invoice`
- `/aws/lambda/parse_invoice`
- `/aws/lambda/get_rental_invoice`
- `/aws/lambda/get_rental_invoices`
- `/aws/lambda/get_user_profile`
- `/aws/lambda/delete_user`
- `/aws/lambda/send_invoice_notification`

## Next Steps
- Some IAM policies are currently AWS-managed - migrate them to Terraform-managed
- Move SNS subscription management to Terraform
    - I would like to define a flow where, whenever a new user installs the app and signs up using their Gmail account, they automatically get configured for push notifications. Right now, this process has to be configured manually
- Add CI/CD workflow
    - I would like to set up a flow where, whenever there any updates or additions to the lambda functions are pushed, it triggers a pipeline which tests the function, and then deploys it
    - GitHub Actions can be used for this
