import os
import sys
import json
import boto3
import logging
from botocore.exceptions import ClientError

print("CWD:", os.getcwd())
print("Files:", os.listdir())
if 'utils' in os.listdir():
    print("\tUtils files: ", os.listdir('./utils'))
print("Sys Path:", sys.path)

# from logging_config import logger
from HyresaviParser import extract_rental_info_from_file

from utils.dynamodb_utils import create_invoice_in_dynamodb
from utils.error_handling import log_and_generate_error_response
from utils.exceptions import S3Error, InvoiceParseError, DatabaseError
from utils.s3_utils import download_file_from_s3


s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb', region_name=os.environ['REGION'])


def lambda_handler(event, context=None):
    try:
        logging.info("Parse_invoice function has started")
        filename = ""
        for record in event['Records']:
            bucket = record['s3']['bucket']['name']
            key = record['s3']['object']['key']
            user_id = key.split('/')[-2]

            filename = download_file_from_s3(s3_client, bucket_name=bucket, s3_key=key)

            # extract text and parse data
            try:
                parsed_data = extract_rental_info_from_file(filename)
                logging.info(f"{filename} parsed successfully!")
            except Exception as e:
                raise InvoiceParseError(f"Could not parse {filename}")

            # insert data into DynamoDB table
            try:
                table = dynamodb.Table(os.environ['DYNAMODB_TABLE'])
                # add invoice ID
                invoice_id = "Invoice_" + filename.split('/')[-1].split('.')[0].split('_')[-1]
                create_invoice_in_dynamodb(table, invoice_id, user_id, parsed_data)

            except ClientError as e:
                raise DatabaseError(f"Could not insert parsed data for {filename} into DB.")

        logging.info("Successfully processed and stored invoice data.")
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