import os
import json
import boto3
import logging
import traceback
from botocore.exceptions import ClientError
from HyresaviParser import extract_rental_info_from_file

from utils.dynamodb_utils import create_invoice_in_dynamodb
from utils.error_handling import log_and_generate_error_response
from utils.exceptions import S3Error, InvoiceParseError, DatabaseError
from utils.s3_utils import download_file_from_s3


s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb', region_name=os.environ['REGION'])


def lambda_handler(event, context=None):
    try:
        print("Parse_invoice function has started")
        filename = ""
        for record in event['Records']:
            print("Downloading file...")
            bucket = record['s3']['bucket']['name']
            key = record['s3']['object']['key']
            user_id = key.split('/')[-2]

            print(f"\tBucket: {bucket}; Key: {key}; UserID: {user_id}")

            filename = download_file_from_s3(s3_client, bucket_name=bucket, s3_key=key)
            print(f"\tFilename: {filename}")

            # extract text and parse data
            try:
                print("Parsing file...")
                parsed_data = extract_rental_info_from_file(filename)
                print(f"\t{filename} parsed successfully!")
                print(f"\tParsed data: {parsed_data}")
            except Exception as e:
                raise InvoiceParseError(f"Could not parse {filename}") from e

            # insert data into DynamoDB table
            try:
                print("Storing data into table...")
                table = dynamodb.Table(os.environ['DYNAMODB_TABLE'])
                print(f"\tTable: {table}")
                # add invoice ID
                invoice_id = "Invoice_" + filename.split('/')[-1].split('.')[0].split('_')[-1]
                print(f"\tInvoice ID: {invoice_id}")
                create_invoice_in_dynamodb(table, invoice_id, user_id, parsed_data)

            except ClientError as e:
                print(traceback.format_exc())
                raise DatabaseError(f"Could not insert parsed data for {filename} into DB.") from e

        print("Successfully processed and stored invoice data.")
        return {
            'statusCode': 200,
            'body': json.dumps({
                'filename': filename,
                'status': 'success'
            })
        }
    except json.JSONDecodeError as e:
        return log_and_generate_error_response(error_code=400, error_message="Invalid JSON in request body", error=e)
    except S3Error as e:
        return log_and_generate_error_response(error_code=500, error_message="Error downloading invoice from S3",
                                               error=e)
    except InvoiceParseError as e:
        return log_and_generate_error_response(error_code=500, error_message="Error parsing invoice", error=e)
    except KeyError as e:
        return log_and_generate_error_response(error_code=400, error_message=f"Missing key in request body: {e}",
                                               error=e)
    except DatabaseError as e:
        return log_and_generate_error_response(error_code=500, error_message=f"Error with data insertion: {e}",
                                               error=e)
    except Exception as e:
        return log_and_generate_error_response(error_code=500, error_message="Internal Server Error", error=e)


if __name__ == '__main__':
    event = {
      "Records": [
        {
          "s3": {
            "bucket": {
              "name": "rental-invoices-bucket"
            },
            "object": {
              "key": "rental-invoices/azy.imtiaz/Hyresavi_1306798107.pdf"
            }
          }
        },
        {
          "s3": {
              "bucket": {
                  "name": "rental-invoices-bucket"
              },
              "object": {
                  "key": "rental-invoices/azy.imtiaz/Hyresavi_1339178608.pdf"
              }
          }
        }
      ]
    }

    lambda_handler(event)