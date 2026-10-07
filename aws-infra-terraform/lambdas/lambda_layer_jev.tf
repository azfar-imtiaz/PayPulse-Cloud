resource "aws_lambda_layer_version" "jev_layer" {
  layer_name          = "jev_layer"
  filename            = "${path.module}/../../lambda_layers/jev/jev_layer.zip"
  source_code_hash    = filebase64sha256("${path.module}/../../lambda_layers/jev/jev_layer.zip")
  compatible_runtimes = ["python3.12"]
  description         = "TypeSafe AI (Jev) SDK for retail email classification"
}
