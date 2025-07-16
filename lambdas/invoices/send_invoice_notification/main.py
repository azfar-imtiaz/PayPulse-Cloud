import os
import json
import boto3
from typing import Dict

sns_client = boto3.client('sns')
sns_topic_arn = os.getenv('SNS_TOPIC_ARN')

def get_fields_for_notification(data: Dict) -> Dict:
    due_date = data['Due Date']['S']
    amount = data['Total Amount']['S']
    return {
        'due_date': due_date,
        'amount': amount
    }


def lambda_handler(event, context):
    for record in event['Records']:
        if record['eventName'] == 'INSERT':
            new_data = record['dynamodb']['NewImage']
            notification_fields = get_fields_for_notification(new_data)

            message = f"New rental invoice of {notification_fields['amount']} SEK with due date of {notification_fields['due_date']} is now available!"

            response = sns_client.publish(
                TopicArn = sns_topic_arn,
                Message=message,
                Subject="New invoice available!"
            )

            print(f"Notification sent: {response}")

    return {
        'statusCode': 200,
        'body': "Notification sent!"
    }
