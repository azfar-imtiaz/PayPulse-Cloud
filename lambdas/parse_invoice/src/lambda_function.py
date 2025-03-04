import json
import boto3
from botocore.exceptions import ClientError

from logging_config import logger
from HyresaviParser import extract_rental_info_from_file


s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb', region_name='eu-west-1')


def lambda_handler(event, context=None):
    logger.info("Lambda function has started")
    filename = ""
    for record in event['Records']:
        bucket = record['s3']['bucket']['name']
        key = record['s3']['object']['key']

        # download the file to /tmp
        filename = f"/tmp/{key.split('/')[-1]}"
        try:
            s3_client.download_file(bucket, key, filename)
            logger.info(f"Downloaded {filename} successfully.")
        except ClientError as e:
            logger.error(f"Error downloading {filename}")
            return {
                'statusCode': 500,
                'body': json.dumps({
                    'filename': filename,
                    'status': 'failure',
                    'error': f"Error: {str(e)}"
                })
            }

        # extract text and parse data
        try:
            parsed_data = extract_rental_info_from_file(filename)
            logger.info(f"{filename} parsed successfully!")
        except Exception as e:
            logger.error(f"Error parsing {filename}: {e}")
            return {
                'statusCode': 500,
                'body': json.dumps({
                    'filename': filename,
                    'status': 'failure',
                    'error': f"Error: {str(e)}"
                })
            }

        # insert data into DynamoDB table
        try:
            table = dynamodb.Table("Wallenstam-Invoices")
            # add invoice ID
            invoice_id = "Invoice_" + filename.split('/')[-1].split('.')[0].split('_')[-1]
            parsed_data['InvoiceID'] = invoice_id
            # insert parsed invoice into table
            table.put_item(Item=parsed_data)
            logger.info("Item added to table!")
        except ClientError as e:
            logger.error(f"Error inserting item into DynamoDB: {e}")
            return {
                'statusCode': 500,
                'body': json.dumps({
                    'filename': filename,
                    'status': 'failure',
                    'error': f"Error: {str(e)}"
                })
            }

    logger.info("Successfully processed and stored invoice data.")
    return {
        'statusCode': 200,
        'body': json.dumps({
            'filename': filename,
            'status': 'success'
        })
    }


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