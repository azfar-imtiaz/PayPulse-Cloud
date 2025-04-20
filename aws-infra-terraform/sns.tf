resource "aws_sns_topic" "new_invoice_notification" {
  name         = var.rental_invoice_notification_topic
  display_name = var.rental_invoice_notification_display_name
}

/*

SNS subscriptions should not be mentioned in the sns.tf file if they are generated programmatically (which we want them to be, in this case)
If I want, I can specify the email one only, since in the case of deployment, the notifications would only be to the app, I think
I have mentioned the code here in case I want to manage the notifications here. NOTE: I will need to import these both things then

resource "aws_sns_topic_subscription" "email_alert" {
  topic_arn = aws_sns_topic.new_invoice_notification.arn
  protocol  = "email"
  endpoint  = "your@email.com"
}

resource "aws_sns_topic_subscription" "ios_push" {
  topic_arn = aws_sns_topic.new_invoice_notification.arn
  protocol  = "application"
  endpoint  = "arn:aws:sns:eu-west-1:123456789012:app/APNS/your-ios-app"
}
*/