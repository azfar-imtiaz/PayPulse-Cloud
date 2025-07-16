import os
import json
import boto3
import logging
import traceback
from botocore.exceptions import ClientError
from HyresaviParser import extract_rental_info_from_file

from utils.dynamodb_utils import create_invoice_in_dynamodb
from utils.responses import success_response, log_and_generate_error_response, ErrorCode
from utils.exceptions import S3Error, InvoiceParseError, DatabaseError
from utils.s3_utils import download_file_from_s3


s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb', region_name=os.environ['REGION'])


def lambda_handler(event, context=None):
    try:
        logging.info("Parse_invoice function has started")
        invoice_id = ""
        filename = ""
        for record in event['Records']:
            logging.info("Downloading file...")
            bucket = record['s3']['bucket']['name']
            key = record['s3']['object']['key']
            user_id = key.split('/')[-2]

            logging.info(f"\tBucket: {bucket}; Key: {key}; UserID: {user_id}")

            filename = download_file_from_s3(s3_client, bucket_name=bucket, s3_key=key)
            logging.info(f"\tFilename: {filename}")

            # extract text and parse data
            try:
                logging.info("Parsing file...")
                parsed_data = extract_rental_info_from_file(filename)
                logging.info(f"\t{filename} parsed successfully!")
                logging.info(f"\tParsed data: {parsed_data}")
            except Exception as e:
                raise InvoiceParseError(f"Could not parse {filename}") from e

            # insert data into DynamoDB table
            try:
                logging.info("Storing data into table...")
                table = dynamodb.Table(os.environ['DYNAMODB_TABLE'])
                logging.info(f"\tTable: {table}")
                # add invoice ID
                invoice_id = "Invoice_" + filename.split('/')[-1].split('.')[0].split('_')[-1]
                logging.info(f"\tInvoice ID: {invoice_id}")
                create_invoice_in_dynamodb(table, invoice_id, user_id, parsed_data)

            except ClientError as e:
                logging.error(traceback.format_exc())
                raise DatabaseError(f"Could not insert parsed data for {filename} into DB.") from e

        logging.info("Successfully processed and stored invoice data.")
        return success_response(
            message=f"Rental invoice {invoice_id} parsed successfully!",
            data={
                'filename': filename
            }
        )
    except json.JSONDecodeError as e:
        return log_and_generate_error_response(ErrorCode.INVALID_JSON, "Invalid JSON in request body", 400, e)

    except DatabaseError as e:
        return log_and_generate_error_response(
            ErrorCode.DEPENDENCY_FAILURE,
            "Database error during insertion of parsed data for invoice",
            502,
            e
        )
    except S3Error as e:
        return log_and_generate_error_response(ErrorCode.DEPENDENCY_FAILURE, "Error creating S3 folder", 502, e)

    except InvoiceParseError as e:
        return log_and_generate_error_response(ErrorCode.INVOICE_PARSE_ERROR, "Error parsing invoice", 500, e)

    except KeyError as e:
        return log_and_generate_error_response(ErrorCode.MISSING_FIELDS, f"Missing key in request body: {e}", 400, e)

    except Exception as e:
        return log_and_generate_error_response(ErrorCode.INTERNAL_SERVER_ERROR, "Internal Server Error", 500, e)


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